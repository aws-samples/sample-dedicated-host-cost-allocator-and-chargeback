#!/usr/bin/env python3
"""
AWS Dedicated Host Cost Allocator - Multi-Account Version
Extends the single-account version to support AWS Organizations with multiple accounts.

Author: AWS Community
License: MIT
"""

import boto3
import csv
import yaml
import argparse
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from cost_allocator import DedicatedHostCostAllocator

class MultiAccountDedicatedHostCostAllocator:
    def __init__(self, config_file='config.yaml'):
        self.config = self.load_config(config_file)
        self.accounts = self.config.get('accounts', [])
        self.tag_keys = self.config.get('tag_keys', ['Department', 'Team', 'Project', 'Environment'])
        
        # Add account context to tag keys
        if 'Account' not in self.tag_keys:
            self.tag_keys.append('Account')
        
        print(f"Multi-Account Cost Allocator initialized for {len(self.accounts)} accounts")
    
    def load_config(self, config_file):
        """Load multi-account configuration"""
        if not os.path.exists(config_file):
            print(f"Error: Config file {config_file} not found")
            print("Create a config.yaml with accounts section. See docs/multi-account-setup.md")
            sys.exit(1)
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if 'accounts' not in config:
            print("Error: No 'accounts' section found in config.yaml")
            print("For single-account usage, use cost_allocator.py instead")
            sys.exit(1)
        
        return config
    
    def assume_role(self, account_id, role_arn, session_name=None):
        """Assume role in target account"""
        if not session_name:
            session_name = f"CostAllocator-{account_id}-{datetime.now().strftime('%Y%m%d')}"
        
        try:
            sts = boto3.client('sts')
            response = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                DurationSeconds=3600  # 1 hour
            )
            
            return boto3.Session(
                aws_access_key_id=response['Credentials']['AccessKeyId'],
                aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                aws_session_token=response['Credentials']['SessionToken']
            )
        except Exception as e:
            print(f"Error assuming role in account {account_id}: {e}")
            return None
    
    def process_account(self, account_config, method='weighted', days_back=30):
        """Process a single account"""
        account_id = account_config['id']
        account_name = account_config.get('name', account_id)
        role_arn = account_config['role']
        regions = account_config.get('regions', ['us-east-1'])
        
        print(f"\nProcessing account: {account_name} ({account_id})")
        
        # Assume role in target account
        session = self.assume_role(account_id, role_arn)
        if not session:
            print(f"  Skipping account {account_id} due to role assumption failure")
            return []
        
        try:
            # Create allocator with assumed role session
            allocator = DedicatedHostCostAllocator(regions=regions, tag_keys=self.tag_keys)
            
            # Override clients to use assumed role session
            allocator.ec2_clients = {}
            for region in regions:
                allocator.ec2_clients[region] = session.client('ec2', region_name=region)
            allocator.ce = session.client('ce', region_name='us-east-1')
            
            # Run allocation for this account (without generating individual CSV)
            # Get hosts and instances
            hosts = allocator.get_dedicated_hosts()
            if not hosts:
                print(f"  No dedicated hosts found in {account_name}")
                return []
            
            hosts = allocator.get_instances_on_hosts(hosts)
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Get costs and calculate allocation
            host_costs = allocator.get_host_costs(start_date, end_date)
            instance_costs = allocator.calculate_costs(hosts, host_costs, method, start_date, end_date)
            
            print(f"  Found {len(hosts)} hosts, {sum(len(h['instances']) for h in hosts.values())} instances")
            print(f"  Allocated ${sum(cost['allocated_cost'] for cost in instance_costs):.2f}")
            
            # Add account context to results
            for cost in instance_costs:
                cost['account_id'] = account_id
                cost['account_name'] = account_name
                cost['account'] = account_name  # For tag-based reporting
            
            print(f"  Processed {len(instance_costs)} instances")
            return instance_costs
            
        except Exception as e:
            print(f"  Error processing account {account_id}: {e}")
            return []
    
    def run_multi_account(self, method='weighted', days_back=30, account_filter=None):
        """Run cost allocation across multiple accounts"""
        print("AWS Dedicated Host Cost Allocator - Multi-Account")
        print("=" * 50)
        
        all_costs = []
        accounts_to_process = self.accounts
        
        # Filter accounts if specified
        if account_filter:
            filter_ids = account_filter.split(',')
            accounts_to_process = [acc for acc in self.accounts if acc['id'] in filter_ids]
            print(f"Processing filtered accounts: {[acc['id'] for acc in accounts_to_process]}")
        
        # Process each account
        for account_config in accounts_to_process:
            account_costs = self.process_account(account_config, method, days_back)
            all_costs.extend(account_costs)
        
        if not all_costs:
            print("\nNo costs found across all accounts")
            return []
        
        # Generate consolidated report
        self.generate_multi_account_report(all_costs, method)
        
        return all_costs
    
    def generate_multi_account_report(self, instance_costs, method):
        """Generate consolidated multi-account report"""
        if not instance_costs:
            print("No costs to report")
            return
        
        # Generate output filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'multi_account_dedicated_host_costs_{method}_{timestamp}.csv'
        
        # Write CSV report
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=instance_costs[0].keys())
            writer.writeheader()
            writer.writerows(instance_costs)
        
        print(f"\nMulti-account report generated: {output_file}")
        
        # Print summary
        total_cost = sum(cost['allocated_cost'] for cost in instance_costs)
        print(f"Total allocated cost across all accounts: ${total_cost:.2f}")
        
        # Summary by account
        account_costs = defaultdict(float)
        for cost in instance_costs:
            account_costs[cost['account_name']] += cost['allocated_cost']
        
        print("\nCost by Account:")
        for account, cost in sorted(account_costs.items()):
            print(f"  {account}: ${cost:.2f}")
        
        # Summary by region
        region_costs = defaultdict(float)
        for cost in instance_costs:
            region_costs[cost['region']] += cost['allocated_cost']
        
        print("\nCost by Region:")
        for region, cost in sorted(region_costs.items()):
            print(f"  {region}: ${cost:.2f}")
        
        # Summary by tags (excluding account since we already showed that)
        for tag_key in self.tag_keys:
            if tag_key.lower() in ['account']:
                continue
                
            tag_costs = defaultdict(float)
            tag_key_lower = tag_key.lower()
            
            for cost in instance_costs:
                if tag_key_lower in cost:
                    tag_costs[cost[tag_key_lower]] += cost['allocated_cost']
            
            if any(v != 'Unknown' for v in tag_costs.keys()):
                print(f"\nCost by {tag_key}:")
                for tag_value, cost in sorted(tag_costs.items()):
                    if tag_value != 'Unknown':
                        print(f"  {tag_value}: ${cost:.2f}")

def main():
    parser = argparse.ArgumentParser(
        description='Multi-Account AWS Dedicated Host Cost Allocator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cost_allocator_multi_account.py --method weighted
  python cost_allocator_multi_account.py --accounts "111111111111,222222222222"
  python cost_allocator_multi_account.py --config multi-account-config.yaml
  python cost_allocator_multi_account.py --method equal --days-back 60
        """
    )
    
    parser.add_argument('--config', default='config.yaml',
                       help='Multi-account configuration file (default: config.yaml)')
    parser.add_argument('--method', choices=['weighted', 'equal'], default='weighted',
                       help='Allocation method (default: weighted)')
    parser.add_argument('--days-back', type=int, default=30,
                       help='Days of cost data to analyze (default: 30)')
    parser.add_argument('--accounts',
                       help='Comma-separated list of account IDs to process (default: all)')
    
    args = parser.parse_args()
    
    try:
        # Initialize multi-account allocator
        allocator = MultiAccountDedicatedHostCostAllocator(config_file=args.config)
        
        # Run multi-account allocation
        costs = allocator.run_multi_account(
            method=args.method,
            days_back=args.days_back,
            account_filter=args.accounts
        )
        
        print(f"\nMulti-account processing complete: {len(costs)} total cost allocations")
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure config.yaml has 'accounts' section")
        print("2. Verify IAM roles exist in target accounts")
        print("3. Check trust relationships allow role assumption")
        print("4. See docs/multi-account-setup.md for detailed setup")

if __name__ == "__main__":
    main()