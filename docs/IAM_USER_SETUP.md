# IAM User Setup — Industrial AI Platform (AWS)

**Account:** `aakumara7` (313092058964)  
**Region:** `ca-central-1`  
**Author:** Ajith Kumara  

---

## Overview

This document covers the one-time setup of an IAM user for programmatic CLI access to the IAP AWS account. This user (`iap-dev-user`) is used by Terraform and the AWS CLI for local development and deployment.

---

## Step 1 — Navigate to IAM Users

1. Sign in to the AWS Console as the root user (`aakumara7`)
2. Go to: https://console.aws.amazon.com/iam/home#/users/create

---

## Step 2 — Specify User Details

| Field | Value |
|-------|-------|
| User name | `iap-dev-user` |
| Console access | Leave unchecked (CLI only) |

Click **Next**.

---

## Step 3 — Set Permissions

1. Select **"Attach policies directly"**
2. Search for `AdministratorAccess`
3. Check the box next to **AdministratorAccess** (AWS managed - job function)

Click **Next**.

> **Note:** AdministratorAccess is used for initial setup only. In production, replace with a least-privilege custom policy scoped to Kinesis, S3, DynamoDB, and IAM for the platform resources only.

---

## Step 4 — Review and Create

Confirm the summary:

| Field | Expected Value |
|-------|----------------|
| User name | `iap-dev-user` |
| Console password type | None |
| Permissions | AdministratorAccess |

Click **Create user**.

---

## Step 5 — Generate Access Keys

1. Click the newly created `iap-dev-user`
2. Go to the **Security credentials** tab
3. Scroll to **Access keys** section
4. Click **Create access key**
5. Select use case: **Command Line Interface (CLI)**
6. Click **Next** → skip description tag → click **Create access key**
7. **Copy both values immediately** — the Secret Access Key is shown only once:
   - Access Key ID: `AKIA...`
   - Secret Access Key: `<secret>`

> **Warning:** Never commit these keys to git. Never paste them in code or config files. Store them only in `~/.aws/credentials`.

---

## Step 6 — Configure AWS CLI Profile

Open PowerShell and run:

```powershell
aws configure --profile iap-dev
```

Enter when prompted:

```
AWS Access Key ID:     <your Access Key ID>
AWS Secret Access Key: <your Secret Access Key>
Default region name:   ca-central-1
Default output format: json
```

---

## Step 7 — Verify the Profile

```powershell
aws sts get-caller-identity --profile iap-dev
```

Expected output:

```json
{
    "UserId": "AIDA...",
    "Account": "313092058964",
    "Arn": "arn:aws:iam::313092058964:user/iap-dev-user"
}
```

If `Account` shows `313092058964` — setup is complete.

---

## Step 8 — Set Profile in PowerShell Session

For Terraform to pick up the profile automatically, set it in your PowerShell session:

```powershell
$env:AWS_PROFILE = "iap-dev"
```

Verify Terraform can authenticate:

```powershell
cd terraform\environments\dev-stage1
terraform init "-backend-config=backend.hcl" -reconfigure
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No valid credential sources` | Profile not set in session | Run `$env:AWS_PROFILE = "iap-dev"` |
| `Account: 246568717136` | Old account credentials still active | Re-run `aws configure --profile iap-dev` with new keys |
| `InvalidClientTokenId` | Wrong Access Key ID entered | Delete key, create a new one, reconfigure |
| `AccessDenied` | Key belongs to wrong account | Check `aws sts get-caller-identity --profile iap-dev` |

---

## Key Reference

| Item | Value |
|------|-------|
| AWS Account ID | `313092058964` |
| IAM User | `iap-dev-user` |
| CLI Profile name | `iap-dev` |
| Region | `ca-central-1` |
| Credentials file | `~/.aws/credentials` |
| Config file | `~/.aws/config` |

---

## Security Reminders

- **Never** commit `~/.aws/credentials` to git
- **Never** hardcode access keys in Terraform `.tfvars` or Python files
- Rotate keys every 90 days (set a calendar reminder)
- Delete the key immediately if accidentally exposed
- Future improvement: replace long-term keys with AWS IAM Identity Center (SSO)
