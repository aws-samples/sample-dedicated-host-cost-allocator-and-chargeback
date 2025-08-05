# AWS Dedicated Host Cost Allocator

A Python tool that automatically allocates AWS Dedicated Host costs to individual EC2 instances based on resource consumption and custom tags, enabling accurate chargeback and cost attribution across teams and departments.

## 🚀 Quick Start

```bash
# 1. Setup (30 seconds)
pip install -r requirements.txt

# 2. Configure AWS credentials (30 seconds)
aws configure

# 3. Run it (1 minute)
# Single account
python cost_allocator.py --method weighted

# Multi-account (requires setup - see Multi-Account Organizations section below)
cp config-multi-account.yaml config.yaml  # Edit with your accounts
python cost_allocator_multi_account.py --method weighted

# Done! Check the generated CSV file
```

### 🔄 For Regular Reports
**Set up automated execution:**

```bash
# Cron job for monthly execution
0 9 1 * * /usr/bin/python3 /path/to/cost_allocator.py --method weighted

# Or use AWS Systems Manager for EC2-based scheduling
```

### 🏢 Multi-Account Organizations
**For organizations with multiple AWS accounts:**

1. **Create trust policy** (save as `trust-policy.json`):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {"AWS": "arn:aws:iam::<MANAGEMENT-ACCOUNT-ID>:root"},
       "Action": "sts:AssumeRole"
     }]
   }
   ```

2. **Create IAM roles** in each member account:
   ```bash
   # Create the role with trust policy
   aws iam create-role --role-name CostAllocatorRole --assume-role-policy-document file://trust-policy.json
   
   # Attach the cost allocator policy (create this first using the IAM policy template above)
   aws iam attach-role-policy --role-name CostAllocatorRole --policy-arn arn:aws:iam::<ACCOUNT-ID>:policy/DedicatedHostCostAllocatorReadOnly
   ```

3. **Configure accounts** in `config-multi-account.yaml`:
   ```yaml
   accounts:
     - id: "<ACCOUNT-ID-1>"
       name: "production"
       role: "arn:aws:iam::<ACCOUNT-ID-1>:role/CostAllocatorRole"
       regions: ["us-east-1", "us-west-2", "eu-west-1"]  # Multiple regions
     - id: "<ACCOUNT-ID-2>"
       name: "development"
       role: "arn:aws:iam::<ACCOUNT-ID-2>:role/CostAllocatorRole"
       regions: ["us-east-1"]  # Single region
   ```
   
   **Region Configuration:**
   - **Single region**: `regions: ["us-east-1"]`
   - **Multiple regions**: `regions: ["us-east-1", "us-west-2", "eu-west-1"]`
   - **All regions**: Add all regions where you have dedicated hosts

4. **Run multi-account script**:
   ```bash
   python cost_allocator_multi_account.py --method weighted
   ```

## ✨ Features

### Core Features
- **Multi-Region Support**: Analyze dedicated hosts across multiple AWS regions
- **Flexible Allocation**: Choose between vCPU-weighted or equal-split methods
- **Tag-Based Reporting**: Generate cost breakdowns by Department, Team, Project, etc.
- **CSV Export**: Detailed reports with timestamps for historical tracking
- **Simple Configuration**: Easy setup via YAML configuration

### Enterprise Features
- **Multi-Account Support**: Cross-account cost allocation
- **SSO Integration**: Works with AWS SSO and federated access
- **BI Integration**: Export formats compatible with Tableau, PowerBI
- **Automated Scheduling**: Cron jobs and task schedulers

## 📋 Prerequisites

- Python 3.7+
- AWS CLI configured with credentials
- AWS credentials with read permissions for EC2 and Cost Explorer
- See troubleshooting section for IAM policy template

## ⚙️ Configuration

### Single Account Configuration
Edit `config.yaml` to customize regions and tags for your environment:

```yaml
regions:
  - us-east-1
  - us-west-2
  - eu-west-1

tag_keys:
  - Department
  - Team
  - Project
  - Environment

allocation:
  days_back: 30
  method: weighted
```

### Multi-Account Configuration
For multi-account setups, each account can have different regions:

```yaml
accounts:
  - id: "<ACCOUNT-ID-1>"
    name: "production"
    role: "arn:aws:iam::<ACCOUNT-ID-1>:role/CostAllocatorRole"
    regions: ["us-east-1", "us-west-2"]  # Production in multiple US regions
  - id: "<ACCOUNT-ID-2>"
    name: "europe-prod"
    role: "arn:aws:iam::<ACCOUNT-ID-2>:role/CostAllocatorRole"
    regions: ["eu-west-1", "eu-central-1"]  # Europe account
```

## 🔧 Usage

### Basic Usage
```bash
# Default weighted allocation
python cost_allocator.py

# Equal split allocation
python cost_allocator.py --method equal

# Specific regions
python cost_allocator.py --regions us-east-1,eu-west-1

# Custom time period
python cost_allocator.py --days-back 60
```

## 🏢 Deployment Options

**Choose the deployment method that fits your needs:**

| Method | Best For | Resources Created | Setup Time |
|--------|----------|-------------------|------------|
| **Local Script** | Testing, one-time analysis | None | 2 minutes |
| **Scheduled Script** | Automated monthly reports | None (cron/scheduler) | 5 minutes |

### 💻 Manual Execution
**Perfect for:** Testing, ad-hoc analysis, development
- **Resources:** Creates no AWS resources
- **Cost:** Free (only API calls)
- **Setup:** Install Python dependencies and run

### 🔄 Scheduled Execution
**Perfect for:** Automated reporting, production use
- **Resources:** None (uses existing compute)
- **Cost:** Free (only API calls)
- **Setup:** Configure cron job or task scheduler

### Command Line Options
```bash
--config CONFIG      Configuration file (default: config.yaml)
--regions REGIONS    Comma-separated AWS regions
--tags TAGS          Comma-separated tag keys
--method METHOD      Allocation method: weighted or equal
--days-back DAYS     Days of cost data to analyze
```

## 📊 Output

### Console Summary
```
AWS Dedicated Host Cost Allocator
========================================
Configuration:
  Regions: us-east-1, us-west-2
  Tag Keys: Department, Team, Project
  Method: weighted
  Days Back: 30

Discovering dedicated hosts...
  Found 2 hosts in us-east-1
  Found 1 hosts in us-west-2
Mapping instances to hosts...
  Found 8 instances on dedicated hosts
Fetching cost data...
  Found costs for 3 host types
Calculating costs using weighted allocation...

Report generated: dedicated_host_costs_vcpu_weighted_20240130_143022.csv
Total allocated cost: $2,847.50

Cost by Region:
  us-east-1: $1,895.00
  us-west-2: $952.50

Cost by Department:
  Engineering: $1,423.75
  Marketing: $947.50
  Finance: $476.25
```

### CSV Report
```csv
region,host_id,instance_id,instance_type,allocated_cost,allocation_method,runtime_hours,vcpu_count,hourly_rate,department,team,project
us-east-1,h-1234567890abcdef0,i-0123456789abcdef0,c5.4xlarge,623.75,vcpu_weighted,720.0,16,0.8663,Engineering,Backend,ProjectA
us-east-1,h-1234567890abcdef0,i-0987654321fedcba0,c5.2xlarge,311.88,vcpu_weighted,720.0,8,0.4332,Marketing,Frontend,ProjectB
```

## 🧮 Allocation Methods

### Weighted Allocation (Recommended)
Distributes costs based on vCPU consumption:
- `c5.large` (2 vCPUs) gets 2/30 of total cost
- `c5.4xlarge` (16 vCPUs) gets 16/30 of total cost

### Equal Split Allocation
Divides costs equally among all instances regardless of size.

## ⏰ AWS Cost Data Timing

AWS Cost Explorer data has a 24-48 hour delay. For immediate testing, use cost data from 2-3 days ago.

## 🔍 Troubleshooting

### No Cost Data Found
- Ensure dedicated hosts have been running for 24-48+ hours
- Verify AWS Cost Explorer permissions
- Check that regions match where hosts are located

### Permission Errors
Ensure your AWS credentials have the required permissions:

**Required AWS Permissions:**
- `ec2:DescribeHosts` - Read dedicated host information
- `ec2:DescribeInstances` - Read EC2 instance details
- `ec2:DescribeInstanceTypes` - Get instance specifications
- `ce:GetCostAndUsage` - Access cost data from Cost Explorer

**IAM Policy Template:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeHosts",
                "ec2:DescribeInstances",
                "ec2:DescribeInstanceTypes"
            ],
            "Resource": "<REPLACE_WITH_YOUR_EC2_RESOURCE_ARNS or what your organisation allows>"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ce:GetCostAndUsage"
            ],
            "Resource": "<REPLACE_WITH_YOUR_COST_EXPLORER_RESOURCE_ARNS or what your organisation allows>"
        }
    ]
}
```

**Resource ARN Examples:**
- EC2 Resources: `arn:aws:ec2:<REGION>:<ACCOUNT-ID>:instance/*` or `arn:aws:ec2:<REGION>:<ACCOUNT-ID>:dedicated-host/*`
- Cost Explorer: `arn:aws:ce:<REGION>:<ACCOUNT-ID>:<RESOURCE>`
- For account-wide access (if required): `arn:aws:ec2:<REGION>:<ACCOUNT-ID>:<RESOURCE>`

**Placeholder Definitions:**
- `<REGION>`: AWS region (e.g., `us-east-1`) 
- `<ACCOUNT-ID>`: Your 12-digit AWS account ID
- `<RESOURCE>`: Specific resource type or `*` for all resources

**Security Best Practices:**
- Replace placeholders with most restrictive ARNs possible for your use case
- Use dedicated service accounts with minimal permissions
- Add condition statements for IP or time-based restrictions
- Regularly audit and rotate access keys
- Consider using AWS SSO/IAM Identity Center for enhanced security

**Create the policy:**
```bash
# Save customized JSON as dedicated-host-policy.json, then:
aws iam create-policy \
  --policy-name DedicatedHostCostAllocatorReadOnly \
  --policy-document file://dedicated-host-policy.json
```

### No Dedicated Hosts Found
- Verify you have dedicated hosts in the specified regions
- Check that hosts are in 'available' state
- Ensure instances are running with 'host' tenancy

## 🔒 Security

This tool follows AWS security best practices:

- **Read-Only Operations**: Only reads AWS data, never modifies infrastructure
- **Least Privilege**: Requires minimal IAM permissions (EC2 describe, Cost Explorer read)
- **No Data Storage**: Processes data in memory, only outputs local CSV files
- **Credential Safety**: Never logs or stores AWS credentials
- **Multi-Account**: Uses cross-account roles with proper trust policies

**Security Considerations:**
- Review the required IAM permissions before deployment
- Use dedicated service accounts with minimal permissions
- Regularly rotate access keys if using programmatic access
- Consider using AWS SSO/IAM Identity Center for enhanced security

## 💰 Cost

This tool is designed to be cost-effective:

- **No Infrastructure**: Runs locally or on existing compute resources
- **API Calls Only**: Only incurs standard AWS API call charges
- **Minimal Usage**: Typical monthly execution costs under $1 for most organizations
- **Cost Breakdown**:
  - EC2 API calls: ~$0.01 per 1000 calls
  - Cost Explorer API: ~$0.01 per request
  - Estimated monthly cost: $0.10 - $1.00 depending on account size

**Cost Optimization:**
- Run monthly instead of daily to minimize API calls
- Use specific regions to reduce discovery overhead
- Consider caching results for frequent analysis


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## 🙏 Acknowledgments

- AWS Cost Explorer API for cost data
- AWS EC2 API for infrastructure discovery

---

**⚠️ Important**: This tool only **reads** AWS data and creates **local CSV files**. The core script is **read-only** and safe to run.