#!/usr/bin/env python3
"""
AWS Dedicated Host Cost Allocator
A tool to allocate AWS Dedicated Host costs to individual EC2 instances for accurate chargeback.

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

class DedicatedHostCostAllocator:
    def __init__(self, regions=None, tag_keys=None):
        self.regions = regions or ['us-east-1', 'us-west-2', 'eu-west-1']
        self.tag_keys = tag_keys or ['Department', 'Team', 'Project', 'Environment']
        
        # Initialize AWS clients
        self.ec2_clients = {}
        for region in self.regions:
            self.ec2_clients[region] = boto3.client('ec2', region_name=region)
        
        self.ce = boto3.client('ce', region_name='us-east-1')
        self.vcpu_cache = {}
        
        # Host family compatibility mapping
        self.host_families = {
            'm5': ['m5'], 'c5': ['c5'], 'r5': ['r5'], 'm6i': ['m6i'], 
            'c6i': ['c6i'], 'r6i': ['r6i'], 'x1e': ['x1e'], 'z1d': ['z1d']
        }
    
    def get_dedicated_hosts(self):
        """Discover all dedicated hosts across regions"""
        print("Discovering dedicated hosts...")
        all_hosts = {}
        
        for region, ec2_client in self.ec2_clients.items():
            try:
                response = ec2_client.describe_hosts()
                for host in response['Hosts']:
                    host_id = f"{region}:{host['HostId']}"
                    host_props = host.get('HostProperties', {})
                    
                    # Extract host family (e.g., 'c5' from 'c5.large')
                    host_family = host_props.get('InstanceFamily', 'Unknown')
                    if host_family == 'Unknown' and 'InstanceType' in host_props:
                        host_family = host_props['InstanceType'].split('.')[0]
                    
                    all_hosts[host_id] = {
                        'region': region,
                        'host_id': host['HostId'],
                        'host_family': host_family,
                        'state': host['State'],
                        'instances': []
                    }
                    
                print(f"  Found {len(response['Hosts'])} hosts in {region}")
            except Exception as e:
                print(f"  Error in {region}: {e}")
        
        return all_hosts
    
    def get_instances_on_hosts(self, hosts):
        """Map EC2 instances to their dedicated hosts"""
        print("Mapping instances to hosts...")
        
        for region, ec2_client in self.ec2_clients.items():
            try:
                response = ec2_client.describe_instances(
                    Filters=[{'Name': 'tenancy', 'Values': ['host']}]
                )
                
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        host_id = instance.get('Placement', {}).get('HostId')
                        full_host_id = f"{region}:{host_id}"
                        
                        if host_id and full_host_id in hosts:
                            instance_info = {
                                'instance_id': instance['InstanceId'],
                                'instance_type': instance['InstanceType'],
                                'region': region,
                                'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])},
                                'launch_time': instance['LaunchTime']
                            }
                            hosts[full_host_id]['instances'].append(instance_info)
                            
            except Exception as e:
                print(f"  Error getting instances in {region}: {e}")
        
        total_instances = sum(len(host['instances']) for host in hosts.values())
        print(f"  Found {total_instances} instances on dedicated hosts")
        return hosts
    
    def get_host_costs(self, start_date, end_date):
        """Retrieve dedicated host costs from AWS Cost Explorer"""
        print("Fetching cost data...")
        
        response = self.ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
                {'Type': 'DIMENSION', 'Key': 'REGION'}
            ],
            Filter={
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': ['Amazon Elastic Compute Cloud - Compute']
                }
            }
        )
        
        host_costs = {}
        for result in response['ResultsByTime']:
            for group in result['Groups']:
                usage_type = group['Keys'][0]
                region = group['Keys'][1]
                
                # Match dedicated host usage patterns
                if 'HostUsage' in usage_type:
                    cost = float(group['Metrics']['BlendedCost']['Amount'])
                    key = f"{region}:{usage_type}"
                    host_costs[key] = host_costs.get(key, 0) + cost
        
        print(f"  Found costs for {len(host_costs)} host types")
        return host_costs
    
    def get_instance_vcpu(self, instance_type, region):
        """Get vCPU count for instance type"""
        cache_key = f"{region}:{instance_type}"
        if cache_key in self.vcpu_cache:
            return self.vcpu_cache[cache_key]
        
        try:
            response = self.ec2_clients[region].describe_instance_types(
                InstanceTypes=[instance_type]
            )
            if response['InstanceTypes']:
                vcpu_count = response['InstanceTypes'][0]['VCpuInfo']['DefaultVCpus']
                self.vcpu_cache[cache_key] = vcpu_count
                return vcpu_count
        except Exception as e:
            print(f"Warning: Could not get vCPU count for {instance_type}: {e}")
            return 1  # Default to 1 vCPU if lookup fails
        
        # Fallback: parse from instance type name
        size_map = {
            'nano': 1, 'micro': 1, 'small': 1, 'medium': 2, 'large': 2,
            'xlarge': 4, '2xlarge': 8, '3xlarge': 12, '4xlarge': 16,
            '6xlarge': 24, '8xlarge': 32, '12xlarge': 48, '16xlarge': 64
        }
        
        if '.' in instance_type:
            size = instance_type.split('.')[1]
            return size_map.get(size, 2)
        return 2
    
    def calculate_costs(self, hosts, host_costs, method='weighted', start_date=None, end_date=None):
        """Calculate per-instance costs based on allocation method"""
        print(f"Calculating costs using {method} allocation...")
        
        instance_costs = []
        billing_hours = (end_date - start_date).total_seconds() / 3600 if start_date and end_date else 720
        
        for host_id, host_info in hosts.items():
            if not host_info['instances']:
                continue
            
            # Find matching host cost
            host_cost = 0
            for cost_key, cost in host_costs.items():
                if host_info['region'] in cost_key and host_info['host_family'] in cost_key:
                    host_cost = cost
                    break
            
            if host_cost == 0:
                print(f"  Warning: No cost found for host {host_info['host_id']}")
                continue
            
            # Calculate runtime for each instance
            instance_runtimes = {}
            for instance in host_info['instances']:
                launch_time = instance['launch_time']
                if launch_time.tzinfo:
                    launch_time = launch_time.replace(tzinfo=None)
                
                if start_date and launch_time < start_date:
                    runtime = billing_hours
                else:
                    runtime = min(billing_hours, (end_date - launch_time).total_seconds() / 3600) if end_date else billing_hours
                
                instance_runtimes[instance['instance_id']] = max(0, runtime)
            
            # Allocate costs
            if method == 'equal':
                # Equal split among instances
                cost_per_instance = host_cost / len(host_info['instances'])
                for instance in host_info['instances']:
                    runtime_ratio = instance_runtimes[instance['instance_id']] / billing_hours
                    allocated_cost = cost_per_instance * runtime_ratio
                    
                    cost_entry = self._create_cost_entry(
                        host_info, instance, allocated_cost, 'equal_split', 
                        instance_runtimes[instance['instance_id']], billing_hours
                    )
                    instance_costs.append(cost_entry)
            
            elif method == 'weighted':
                # vCPU-weighted allocation
                total_weighted_runtime = 0
                instance_weights = {}
                
                for instance in host_info['instances']:
                    vcpu = self.get_instance_vcpu(instance['instance_type'], instance['region'])
                    runtime = instance_runtimes[instance['instance_id']]
                    instance_weights[instance['instance_id']] = vcpu
                    total_weighted_runtime += vcpu * runtime
                
                for instance in host_info['instances']:
                    vcpu = instance_weights[instance['instance_id']]
                    runtime = instance_runtimes[instance['instance_id']]
                    
                    if total_weighted_runtime > 0:
                        weighted_runtime = vcpu * runtime
                        allocated_cost = (weighted_runtime / total_weighted_runtime) * host_cost
                    else:
                        allocated_cost = 0
                    
                    cost_entry = self._create_cost_entry(
                        host_info, instance, allocated_cost, 'vcpu_weighted',
                        runtime, billing_hours, vcpu
                    )
                    instance_costs.append(cost_entry)
        
        return instance_costs
    
    def _create_cost_entry(self, host_info, instance, cost, method, runtime, billing_hours, vcpu=None):
        """Create a cost entry record"""
        entry = {
            'region': host_info['region'],
            'host_id': host_info['host_id'],
            'instance_id': instance['instance_id'],
            'instance_type': instance['instance_type'],
            'allocated_cost': round(cost, 2),
            'allocation_method': method,
            'runtime_hours': round(runtime, 1),
            'billing_period_hours': round(billing_hours, 1)
        }
        
        if vcpu:
            entry['vcpu_count'] = vcpu
            entry['hourly_rate'] = round(cost / runtime, 4) if runtime > 0 else 0
        
        # Add tag values
        for tag_key in self.tag_keys:
            entry[tag_key.lower()] = instance['tags'].get(tag_key, 'Unknown')
        
        return entry
    
    def generate_report(self, instance_costs, output_file=None):
        """Generate CSV report and summary"""
        if not instance_costs:
            print("No costs to report")
            return
        
        # Generate output filename
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            method = instance_costs[0]['allocation_method']
            output_file = f'dedicated_host_costs_{method}_{timestamp}.csv'
        
        # Write CSV report
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=instance_costs[0].keys())
            writer.writeheader()
            writer.writerows(instance_costs)
        
        print(f"\nReport generated: {output_file}")
        
        # Print summary
        total_cost = sum(cost['allocated_cost'] for cost in instance_costs)
        print(f"Total allocated cost: ${total_cost:.2f}")
        
        # Summary by region
        region_costs = defaultdict(float)
        for cost in instance_costs:
            region_costs[cost['region']] += cost['allocated_cost']
        
        print("\nCost by Region:")
        for region, cost in sorted(region_costs.items()):
            print(f"  {region}: ${cost:.2f}")
        
        # Summary by tags
        for tag_key in self.tag_keys:
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
    
    def run(self, method='weighted', days_back=30):
        """Main execution method"""
        print("AWS Dedicated Host Cost Allocator")
        print("=" * 40)
        
        # Set date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        print(f"Analyzing period: {start_date.date()} to {end_date.date()}")
        
        # Execute allocation process
        hosts = self.get_dedicated_hosts()
        if not hosts:
            print("No dedicated hosts found in specified regions")
            return
        
        hosts = self.get_instances_on_hosts(hosts)
        host_costs = self.get_host_costs(start_date, end_date)
        instance_costs = self.calculate_costs(hosts, host_costs, method, start_date, end_date)
        
        self.generate_report(instance_costs)
        return instance_costs

def load_config(config_file='config.yaml'):
    """Load configuration from YAML file"""
    if not os.path.exists(config_file):
        return {
            'regions': ['us-east-1', 'us-west-2', 'eu-west-1'],
            'tag_keys': ['Department', 'Team', 'Project', 'Environment'],
            'days_back': 30,
            'method': 'weighted'
        }
    
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(
        description='Allocate AWS Dedicated Host costs to EC2 instances',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cost_allocator.py
  python cost_allocator.py --method equal
  python cost_allocator.py --regions us-east-1,eu-west-1
  python cost_allocator.py --config my-config.yaml
        """
    )
    
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file (default: config.yaml)')
    parser.add_argument('--regions', 
                       help='Comma-separated AWS regions')
    parser.add_argument('--tags',
                       help='Comma-separated tag keys for allocation')
    parser.add_argument('--method', choices=['weighted', 'equal'], default='weighted',
                       help='Allocation method (default: weighted)')
    parser.add_argument('--days-back', type=int, default=30,
                       help='Days of cost data to analyze (default: 30)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Override with command line arguments
    regions = args.regions.split(',') if args.regions else config.get('regions', [])
    tag_keys = args.tags.split(',') if args.tags else config.get('tag_keys', [])
    method = args.method or config.get('method', 'weighted')
    days_back = args.days_back or config.get('days_back', 30)
    
    if not regions:
        print("Error: No regions specified")
        sys.exit(1)
    
    print(f"Configuration:")
    print(f"  Regions: {', '.join(regions)}")
    print(f"  Tag Keys: {', '.join(tag_keys)}")
    print(f"  Method: {method}")
    print(f"  Days Back: {days_back}")
    print()
    
    # Run allocation
    try:
        allocator = DedicatedHostCostAllocator(regions=regions, tag_keys=tag_keys)
        allocator.run(method=method, days_back=days_back)
    except Exception as e:
        print(f"Error: {e}")
        print("\nRequired AWS permissions:")
        print("- ec2:DescribeHosts")
        print("- ec2:DescribeInstances") 
        print("- ec2:DescribeInstanceTypes")
        print("- ce:GetCostAndUsage")

if __name__ == "__main__":
    main()