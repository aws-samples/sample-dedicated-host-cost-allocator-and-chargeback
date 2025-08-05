# 🎯 Quick Decision Guide

**New to this tool? Choose your approach:**

## 💻 Manual Execution
**Perfect for:** Testing, one-time analysis, learning
- **Time:** 2 minutes setup
- **Cost:** $0 (only API calls)
- **Resources:** None created

```bash
pip install -r requirements.txt
aws configure
python cost_allocator.py --method weighted
```

**Result:** CSV file with cost allocation in current directory

---

## 🔄 Scheduled Execution
**Perfect for:** Regular monthly reports, production use
- **Time:** 5 minutes setup
- **Cost:** $0 (only API calls)
- **Resources:** None created

```bash
# Set up cron job for monthly execution
0 9 1 * * /usr/bin/python3 /path/to/cost_allocator.py --method weighted
```

**Result:** Automated monthly CSV reports

---

## 🏢 Multi-Account Organizations
**Perfect for:** Enterprise environments with multiple AWS accounts
- **Time:** 15+ minutes setup (IAM roles required)
- **Cost:** $0 (only API calls)
- **Resources:** Cross-account IAM roles

```bash
# After setting up cross-account roles
python cost_allocator_multi_account.py --method weighted
```

**Result:** Consolidated reports across all accounts

See [Multi-Account Setup](docs/multi-account-setup.md) for detailed configuration.

---

# 🆘 Still Not Sure?

**Start with Manual Execution** - it's safe, fast, and creates no AWS resources. You can always add automation later!

**Need help?** Check the main [README.md](README.md) for detailed instructions.