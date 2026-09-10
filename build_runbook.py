"""Build IAP_AWS_Ops_Runbook.xlsx — run with: python build_runbook.py"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = openpyxl.Workbook()

HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=10)
SEC_FILL = PatternFill("solid", fgColor="D6E4F7")
SEC_FONT = Font(name="Arial", bold=True, color="1F3864", size=10)
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
WARN_FONT = Font(name="Arial", bold=True, color="7F6000", size=9)
OK_FILL  = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="BDD7EE")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

def hdr(ws, row, col, text, width=None):
    c = ws.cell(row=row, column=col, value=text)
    c.font = HDR_FONT; c.fill = HDR_FILL
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = BORDER
    if width: ws.column_dimensions[get_column_letter(col)].width = width

def sec(ws, row, col, text, span=None):
    c = ws.cell(row=row, column=col, value=text)
    c.font = SEC_FONT; c.fill = SEC_FILL
    c.alignment = Alignment(horizontal="left", vertical="center")
    c.border = BORDER
    if span:
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col+span-1)

def body(ws, row, col, text, mono=False, bold=False, fill=None):
    c = ws.cell(row=row, column=col, value=text)
    c.font = Font(name="Courier New" if mono else "Arial", size=9, bold=bold)
    c.alignment = Alignment(vertical="top", wrap_text=True)
    c.border = BORDER
    if fill: c.fill = fill

def warn(ws, row, col, text, span=None):
    c = ws.cell(row=row, column=col, value=text)
    c.font = WARN_FONT; c.fill = WARN_FILL
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    c.border = BORDER
    if span:
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col+span-1)

def rh(ws, row, h): ws.row_dimensions[row].height = h

def make_title(ws, text, cols=4):
    ws.merge_cells(f"A1:{get_column_letter(cols)}1")
    c = ws["A1"]; c.value = text
    c.font = Font(name="Arial", bold=True, size=14, color="1F3864")
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.fill = PatternFill("solid", fgColor="EBF3FB"); rh(ws, 1, 30)

# ── TAB 1: Overview ──────────────────────────────────────────────────────
ws = wb.active; ws.title = "Overview"
ws.sheet_view.showGridLines = False
make_title(ws, "Industrial AI Platform — AWS Ops Runbook", cols=6)
ws.merge_cells("A2:F2")
ws["A2"].value = "Account: 246568717136  |  Region: ca-central-1  |  Profile: iap-dev  |  Stage 1 (ephemeral)"
ws["A2"].font = Font(name="Arial", size=10, color="595959")
ws["A2"].alignment = Alignment(horizontal="center")
rh(ws, 2, 20); rh(ws, 3, 8)

for col, (txt, w) in enumerate([
    ("Tab",12),("Technology",22),("Purpose",40),
    ("Key Commands",35),("Cost",20),("Status",14)
], 1):
    hdr(ws, 4, col, txt, w)
rh(ws, 4, 24)

ov_rows = [
    ("Terraform","Terraform IaC","Init/Plan/Apply/Destroy Stage 1","terraform plan/apply/destroy","~$0.015/hr Kinesis only","✅ Ready"),
    ("Kinesis","Amazon Kinesis","Telemetry stream — 1 shard 24h","aws kinesis list-streams","⚠️ $0.015/shard-hr","🔴 Needs account activation"),
    ("S3","Amazon S3","Bronze lake bucket SSE AES256","aws s3 ls / cp / rb","Free Tier (first 5 GB)","✅ Deployed"),
    ("DynamoDB","Amazon DynamoDB","Consumer checkpoints table","aws dynamodb scan","Free Tier (25 GB)","✅ Deployed"),
    ("IAM","AWS IAM","Consumer + Producer roles","aws iam list-roles","No cost","✅ Deployed"),
    ("Smoke Test","End-to-End Test","3 events → verify S3 JSONL","python smoke_test_stage1.py","~$0.001","⏳ Pending Kinesis"),
    ("Mictrack MP91","Edge Device","4G OBD tracker → TCP → Kinesis","SMS: SERVER,1,<ip>,5013,0#","IoT SIM ~$10/mo","📦 In transit (~15 days)"),
    ("Git Commands","Git / GitHub","Commands for Ajith to run manually","git add / commit / push","No cost","📋 Reference only"),
]
for i, (tab,tech,purpose,cmds,cost,status) in enumerate(ov_rows, 5):
    body(ws,i,1,tab,bold=True); body(ws,i,2,tech); body(ws,i,3,purpose)
    body(ws,i,4,cmds,mono=True)
    body(ws,i,5,cost,fill=WARN_FILL if "⚠️" in cost else None)
    body(ws,i,6,status); rh(ws,i,18)

r = len(ov_rows)+6
ws.merge_cells(f"A{r}:F{r}")
warn(ws,r,1,"⚠️  COST GUARD: Kinesis = $0.015/shard-hr. Run `terraform destroy` immediately after smoke test. "
           "S3 + DynamoDB are within Free Tier. Never leave Stage 1 running overnight.",6)
rh(ws,r,30)

# ── TAB 2: Terraform ─────────────────────────────────────────────────────
ws = wb.create_sheet("Terraform"); ws.sheet_view.showGridLines = False
make_title(ws, "Terraform — Stage 1 Ops")
for col,(txt,w) in enumerate([("Step",6),("Action",24),("Command (PowerShell)",70),("Notes",40)],1):
    hdr(ws,2,col,txt,w)
rh(ws,2,22)

tf_rows = [
    ("SETUP",None,None,None),
    ("1","Change dir",r"cd C:\Users\Laptop\Documents\workspace\industrial-ai-platform-aws\terraform\environments\dev-stage1",""),
    ("2","Set profile","set AWS_PROFILE=iap-dev","Or use --profile iap-dev per command"),
    ("3","Verify identity","aws sts get-caller-identity --profile iap-dev","Should show account 246568717136"),
    ("INIT",None,None,None),
    ("4","Init remote state",'terraform init "-backend-config=backend.hcl"',"Quotes required in PowerShell"),
    ("PLAN",None,None,None),
    ("5","Plan Stage 1",'terraform plan "-var-file=terraform.tfvars" "-out=stage1.tfplan"',"Review — 3 resources after partial apply (S3/DDB/IAM already exist)"),
    ("APPLY",None,None,None),
    ("6","Apply plan",'terraform apply "stage1.tfplan"',"⚠️ Kinesis billing starts the moment it's created"),
    ("7","Show outputs","terraform output","Note: kinesis_stream_name, s3_bucket, dynamodb_checkpoint_table"),
    ("DESTROY — run immediately after smoke test",None,None,None),
    ("8","Destroy Kinesis only",'terraform destroy "-var-file=terraform.tfvars" -target=aws_kinesis_stream.telemetry',"Fastest cost-stop — S3/DDB stay"),
    ("9","Full destroy all Stage 1",'terraform destroy "-var-file=terraform.tfvars"',"Type 'yes' to confirm. 11 resources destroyed."),
    ("TROUBLESHOOT",None,None,None),
    ("T1","Too many arguments error","Use quoted flags: terraform plan \"-var-file=terraform.tfvars\"","PowerShell requires quotes around flag=value"),
    ("T2","Stale plan error","Re-run: terraform plan ... -out=stage1.tfplan  then  terraform apply stage1.tfplan","State changed since last plan"),
    ("T3","SubscriptionRequiredException","Complete AWS account registration: Billing > upgrade Free Plan","Free Plan blocks Kinesis. $100 credit absorbs all charges."),
    ("T4","dynamodb_table deprecated warning","Harmless in Terraform 1.15.8. use_lockfile=true in future.",""),
    ("T5","AES256 sse_algorithm error (fixed)","Was incorrectly set to aws:s3 — corrected to AES256 in main.tf","Already fixed"),
]
r=3
for step,action,cmd,note in tf_rows:
    if action is None: sec(ws,r,1,f"── {step} ──",span=4)
    else:
        body(ws,r,1,step,bold=True); body(ws,r,2,action)
        body(ws,r,3,cmd,mono=True); body(ws,r,4,note)
    rh(ws,r,32 if cmd and len(str(cmd))>60 else 20); r+=1

# ── TAB 3: Kinesis ───────────────────────────────────────────────────────
ws = wb.create_sheet("Kinesis"); ws.sheet_view.showGridLines = False
make_title(ws, "Amazon Kinesis Data Streams")
for col,(txt,w) in enumerate([("Category",20),("Detail",30),("Value / Command",65),("Notes",35)],1):
    hdr(ws,2,col,txt,w)
rh(ws,2,22)

kin_rows = [
    ("CONFIG",None,None,None),
    ("Stream name","Terraform output","iap-dev-telemetryhub","env: KINESIS_STREAM_NAME=iap-dev-telemetryhub"),
    ("Shard count","Provisioned mode","1 shard","1 MB/s in, 2 MB/s out"),
    ("Retention","Hours","24 hours (free)","Extended retention >24h costs extra"),
    ("Encryption","KMS key","alias/aws/kinesis (AWS-managed)","No charge for AWS-managed key"),
    ("Region","AWS region","ca-central-1","Canada Central"),
    ("COST",None,None,None),
    ("Shard rate","Per shard-hour","$0.015 USD","1-hr smoke test ≈ $0.015"),
    ("Data PUT","Per 1M payload units","$0.014 USD","Negligible for smoke test (3 events)"),
    ("Estimated total","1-hour test","~$0.03 USD","Covered by $100 credit on account"),
    ("AWS CLI COMMANDS",None,None,None),
    ("List streams","Verify exists","aws kinesis list-streams --profile iap-dev --region ca-central-1",""),
    ("Describe stream","Check shard/status","aws kinesis describe-stream-summary --stream-name iap-dev-telemetryhub --profile iap-dev --region ca-central-1",""),
    ("Put test record","Manual put",'aws kinesis put-record --stream-name iap-dev-telemetryhub --partition-key test --data "dGVzdA==" --profile iap-dev --region ca-central-1','data=base64("test")'),
    ("Get shard iterator","Read records","aws kinesis get-shard-iterator --stream-name iap-dev-telemetryhub --shard-id shardId-000000000000 --shard-iterator-type TRIM_HORIZON --profile iap-dev --region ca-central-1",""),
    ("PYTHON PRODUCER",None,None,None),
    ("Import","","from src.infrastructure.kinesis_producer import KinesisProducer",""),
    ("Send events","","producer = KinesisProducer(stream_name='iap-dev-telemetryhub')\nproducer.send_events(events)","events = list of dicts"),
    ("TERRAFORM",None,None,None),
    ("Resource","HCL",'resource "aws_kinesis_stream" "telemetry"',"main.tf line 89"),
    ("Destroy only","Target destroy","terraform destroy \"-var-file=terraform.tfvars\" -target=aws_kinesis_stream.telemetry","Keeps S3/DDB"),
]
r=3
for cat,detail,val,note in kin_rows:
    if detail is None: sec(ws,r,1,f"── {cat} ──",span=4)
    else:
        body(ws,r,1,cat,bold=True); body(ws,r,2,detail)
        body(ws,r,3,val,mono=True); body(ws,r,4,note)
    rh(ws,r,30 if val and len(str(val))>60 else 18); r+=1
warn(ws,r,1,"⚠️  DESTROY Kinesis immediately after smoke test: terraform destroy ... -target=aws_kinesis_stream.telemetry",4); rh(ws,r,24)

# ── TAB 4: S3 ────────────────────────────────────────────────────────────
ws = wb.create_sheet("S3"); ws.sheet_view.showGridLines = False
make_title(ws, "Amazon S3 — Bronze Lake Bucket")
for col,(txt,w) in enumerate([("Category",20),("Detail",30),("Value / Command",65),("Notes",35)],1):
    hdr(ws,2,col,txt,w); rh(ws,2,22)

s3_rows = [
    ("CONFIG",None,None,None),
    ("Bucket name","Resource output","iap-dev-lake-246568717136","env: S3_BUCKET=iap-dev-lake-246568717136"),
    ("Encryption","SSE algorithm","AES256 (AWS S3-managed)","Upgrade to aws:kms in full dev env"),
    ("Versioning","Status","Enabled","Protects against accidental deletes"),
    ("Public access","All blocks","All true — TLS-only policy applied","DenyNonTLS bucket policy attached"),
    ("force_destroy","Stage 1 setting","true","terraform destroy works even with objects"),
    ("COST",None,None,None),
    ("Storage","First 5 GB","Free Tier","Smoke test objects are tiny"),
    ("Requests","PUT/GET","Free Tier (2k PUT, 20k GET/month)",""),
    ("AWS CLI COMMANDS",None,None,None),
    ("List all","","aws s3 ls s3://iap-dev-lake-246568717136/ --recursive --profile iap-dev",""),
    ("List bronze","","aws s3 ls s3://iap-dev-lake-246568717136/bronze/ --profile iap-dev",""),
    ("Download objects","","aws s3 cp s3://iap-dev-lake-246568717136/bronze/telemetry/ ./out/ --recursive --profile iap-dev",""),
    ("Empty bucket","Before destroy","aws s3 rm s3://iap-dev-lake-246568717136/ --recursive --profile iap-dev","Handled automatically by force_destroy=true in Terraform"),
    ("OBJECT LAYOUT",None,None,None),
    ("Bronze","Raw ingestion","bronze/telemetry/YYYY/MM/DD/HH/*.jsonl","Written by consumer"),
    ("DLQ","Dead-letter queue","bronze/dlq/YYYY/MM/DD/*.jsonl","Poison records that failed parsing"),
    ("Silver","Transformed","silver/telemetry/ (Delta table)","Full dev env"),
    ("Gold","Aggregated","gold/vehicle_metrics/ (Delta table)","Full dev env"),
    ("TERRAFORM",None,None,None),
    ("Resource","HCL",'resource "aws_s3_bucket" "lake"',"main.tf line 25"),
    ("Keep S3","Destroy Kinesis only","terraform destroy \"-var-file=terraform.tfvars\" -target=aws_kinesis_stream.telemetry","S3 within Free Tier — safe to keep"),
]
r=3
for cat,detail,val,note in s3_rows:
    if detail is None: sec(ws,r,1,f"── {cat} ──",span=4)
    else:
        body(ws,r,1,cat,bold=True); body(ws,r,2,detail)
        body(ws,r,3,val,mono=True); body(ws,r,4,note)
    rh(ws,r,24 if val and len(str(val))>50 else 18); r+=1

# ── TAB 5: DynamoDB ──────────────────────────────────────────────────────
ws = wb.create_sheet("DynamoDB"); ws.sheet_view.showGridLines = False
make_title(ws, "Amazon DynamoDB — Consumer Checkpoints")
for col,(txt,w) in enumerate([("Category",20),("Detail",30),("Value / Command",65),("Notes",35)],1):
    hdr(ws,2,col,txt,w); rh(ws,2,22)

ddb_rows = [
    ("CONFIG",None,None,None),
    ("Table name","Resource output","iap-dev-checkpoints","env: DYNAMODB_TABLE=iap-dev-checkpoints"),
    ("Billing","Capacity mode","PAY_PER_REQUEST (on-demand)","Free Tier: 25 GB storage"),
    ("Hash key","Partition key","shard_id (String)","Kinesis shard ID"),
    ("Range key","Sort key","stream_name (String)","Kinesis stream name"),
    ("Encryption","SSE","Enabled (AWS-managed)",""),
    ("PITR","Point-in-time recovery","Enabled — 35-day recovery window",""),
    ("COST",None,None,None),
    ("Free Tier","Storage","First 25 GB free","Checkpoint data < 1 MB"),
    ("Free Tier","Throughput","25 WCU + 25 RCU/second free","Smoke test well within limit"),
    ("AWS CLI COMMANDS",None,None,None),
    ("Scan all","","aws dynamodb scan --table-name iap-dev-checkpoints --profile iap-dev --region ca-central-1",""),
    ("Get item","",'aws dynamodb get-item --table-name iap-dev-checkpoints --key \'{"shard_id":{"S":"shardId-000000000000"},"stream_name":{"S":"iap-dev-telemetryhub"}}\' --profile iap-dev --region ca-central-1',""),
    ("Delete item","Clear checkpoint",'aws dynamodb delete-item --table-name iap-dev-checkpoints --key \'{"shard_id":{"S":"shardId-000000000000"},"stream_name":{"S":"iap-dev-telemetryhub"}}\' --profile iap-dev --region ca-central-1',""),
    ("CHECKPOINT LOGIC",None,None,None),
    ("Dev mode","File-based","checkpoint/{stream_name}/{shard_id}.json","CHECKPOINT_BACKEND=file"),
    ("Prod mode","DynamoDB","PutItem / GetItem on shard_id + stream_name","CHECKPOINT_BACKEND=dynamodb"),
    ("P0-01 fix","Ordering guarantee","Sequence number per shard — preserves in-order processing","Critical correctness fix"),
    ("TERRAFORM",None,None,None),
    ("Resource","HCL",'resource "aws_dynamodb_table" "checkpoints"',"main.tf line 105"),
]
r=3
for cat,detail,val,note in ddb_rows:
    if detail is None: sec(ws,r,1,f"── {cat} ──",span=4)
    else:
        body(ws,r,1,cat,bold=True); body(ws,r,2,detail)
        body(ws,r,3,val,mono=True); body(ws,r,4,note)
    rh(ws,r,28 if val and len(str(val))>60 else 18); r+=1

# ── TAB 6: IAM ───────────────────────────────────────────────────────────
ws = wb.create_sheet("IAM"); ws.sheet_view.showGridLines = False
make_title(ws, "AWS IAM — Roles & Policies")
for col,(txt,w) in enumerate([("Role / Principal",24),("Permission / Action",40),("Resource",45),("Notes",28)],1):
    hdr(ws,2,col,txt,w); rh(ws,2,22)

iam_rows = [
    ("CLI USER",None,None,None),
    ("ajith-dev-cli","AdministratorAccess","arn:aws:iam::246568717136:user/ajith-dev-cli","Profile: iap-dev. Reduce to least-privilege before production."),
    ("CONSUMER ROLE — iap-dev-consumer",None,None,None),
    ("iap-dev-consumer","kinesis:GetRecords GetShardIterator DescribeStream ListShards ListStreams","arn:aws:kinesis:ca-central-1:246568717136:stream/iap-dev-telemetryhub","Read-only Kinesis access"),
    ("iap-dev-consumer","kms:Decrypt GenerateDataKey","* (condition: kms:ViaService=kinesis.ca-central-1.amazonaws.com)","KMS for Kinesis decryption"),
    ("iap-dev-consumer","s3:PutObject GetObject ListBucket","arn:aws:s3:::iap-dev-lake-246568717136/*","Write bronze + DLQ to S3"),
    ("iap-dev-consumer","dynamodb:GetItem PutItem UpdateItem DeleteItem Scan Query","arn:aws:dynamodb:ca-central-1:246568717136:table/iap-dev-checkpoints","Checkpoint read/write"),
    ("PRODUCER ROLE — iap-dev-producer",None,None,None),
    ("iap-dev-producer","kinesis:PutRecord PutRecords DescribeStream DescribeStreamSummary","arn:aws:kinesis:ca-central-1:246568717136:stream/iap-dev-telemetryhub","Write-only Kinesis"),
    ("iap-dev-producer","kms:GenerateDataKey Decrypt","* (condition: kms:ViaService=kinesis.ca-central-1.amazonaws.com)","KMS for Kinesis encryption"),
    ("TRUST POLICIES",None,None,None),
    ("Consumer + Producer","sts:AssumeRole","ec2.amazonaws.com","EC2 instances can assume these roles"),
    ("AWS CLI COMMANDS",None,None,None),
    ("List roles","aws iam list-roles --profile iap-dev | grep iap-dev","",""),
    ("Describe role","aws iam get-role --role-name iap-dev-consumer --profile iap-dev","",""),
    ("List policies","aws iam list-role-policies --role-name iap-dev-consumer --profile iap-dev","",""),
]
r=3
for col1,col2,col3,col4 in iam_rows:
    if col2 is None: sec(ws,r,1,f"── {col1} ──",span=4)
    else:
        body(ws,r,1,col1,bold=True); body(ws,r,2,col2,mono=True)
        body(ws,r,3,col3,mono=True); body(ws,r,4,col4)
    rh(ws,r,28 if col2 and len(str(col2))>50 else 18); r+=1

# ── TAB 7: Smoke Test ────────────────────────────────────────────────────
ws = wb.create_sheet("Smoke Test"); ws.sheet_view.showGridLines = False
make_title(ws, "Stage 1 Smoke Test — End-to-End Verification", cols=5)
for col,(txt,w) in enumerate([("#",5),("Step",30),("Command / Action",65),("Expected Result",35),("✓",10)],1):
    hdr(ws,2,col,txt,w); rh(ws,2,22)

smoke_rows = [
    ("PRE-CONDITIONS",None,None,None,None),
    ("P1","Verify outputs","terraform output","Shows stream/bucket/table names",""),
    ("P2","Verify identity","aws sts get-caller-identity --profile iap-dev","Account 246568717136",""),
    ("P3","Stream ACTIVE","aws kinesis describe-stream-summary --stream-name iap-dev-telemetryhub --profile iap-dev --region ca-central-1","StreamStatus: ACTIVE",""),
    ("ENV SETUP",None,None,None,None),
    ("1","Set env vars","set KINESIS_STREAM_NAME=iap-dev-telemetryhub\nset S3_BUCKET=iap-dev-lake-246568717136\nset DYNAMODB_TABLE=iap-dev-checkpoints\nset AWS_PROFILE=iap-dev\nset AWS_DEFAULT_REGION=ca-central-1","No output",""),
    ("SEND EVENTS",None,None,None,None),
    ("2","Run simulator","python edge/run_simulator.py --count 3","3 events sent, no errors",""),
    ("VERIFY S3",None,None,None,None),
    ("3","List S3 bronze","aws s3 ls s3://iap-dev-lake-246568717136/bronze/telemetry/ --recursive --profile iap-dev","Shows .jsonl file",""),
    ("4","Download & inspect","aws s3 cp s3://iap-dev-lake-246568717136/bronze/telemetry/ ./smoke_out/ --recursive --profile iap-dev","JSONL with 3 records",""),
    ("VERIFY DYNAMODB",None,None,None,None),
    ("5","Check checkpoint","aws dynamodb scan --table-name iap-dev-checkpoints --profile iap-dev --region ca-central-1","Item with sequence_number",""),
    ("CLEANUP — MANDATORY",None,None,None,None),
    ("6","⚠️ Destroy Kinesis","terraform destroy \"-var-file=terraform.tfvars\" -target=aws_kinesis_stream.telemetry","1 resource destroyed",""),
    ("7","Verify stream gone","aws kinesis list-streams --profile iap-dev --region ca-central-1","Empty StreamNames list",""),
    ("8","(Optional) Full destroy","terraform destroy \"-var-file=terraform.tfvars\"","11 resources destroyed",""),
]
r=3
for row in smoke_rows:
    num,step,cmd,expected,pf = row
    if step is None: sec(ws,r,1,f"── {num} ──",span=5)
    else:
        body(ws,r,1,num,bold=True); body(ws,r,2,step)
        body(ws,r,3,cmd,mono=True); body(ws,r,4,expected); body(ws,r,5,pf)
    rh(ws,r,40 if cmd and "\n" in str(cmd) else 22); r+=1

# ── TAB 8: Mictrack MP91 ─────────────────────────────────────────────────
ws = wb.create_sheet("Mictrack MP91"); ws.sheet_view.showGridLines = False
make_title(ws, "Mictrack MP91 — 4G OBD Edge Device")
for col,(txt,w) in enumerate([("Phase",20),("Action",28),("Detail / Command",55),("Notes",40)],1):
    hdr(ws,2,col,txt,w); rh(ws,2,22)

mp91_rows = [
    ("DEVICE SPECS",None,None,None),
    ("Model","","Mictrack MP91","4G FDD LTE OBD-II plug-in tracker"),
    ("LTE bands","","B1/B2/B3/B4/B5/B7/B8/B28/B66","B4/B7/B66 cover Canadian carriers (Koodo/Telus/Rogers)"),
    ("Protocol","","Open ASCII over TCP","NMEA-like lines, parseable"),
    ("Config method","","SMS commands to device SIM number",""),
    ("Price","","USD $39.99 (~CAD $57.59)","Amazon.com — ~15 days to Ontario"),
    ("SIM SETUP",None,None,None),
    ("Carrier","Recommended","Koodo IoT SIM (or Telus IoT)","Confirmed IoT SIM support in Ontario, Canada"),
    ("APN","Koodo","sp.koodo.com","Standard Koodo data APN"),
    ("Cost","IoT plan","~$10/month","Low-data plan sufficient for telemetry"),
    ("SMS CONFIG COMMANDS",None,None,None),
    ("Set server","Point device to EC2","SERVER,1,<EC2_PUBLIC_IP>,5013,0#","Port 5013 = GT06 / Traccar compatible"),
    ("Check status","Query device","STATUS#","Device replies with GPS + signal info"),
    ("Set interval","Reporting frequency","TIMER,30#","Every 30 seconds (adjust as needed)"),
    ("Restart","Apply new config","RESTART#","Required after SERVER command"),
    ("EC2 TCP LISTENER",None,None,None),
    ("Instance","Free Tier","t2.micro or t3.micro","750 hrs/month free"),
    ("Port","TCP inbound","5013","Open in EC2 Security Group inbound rules"),
    ("Listener script","File path","edge/tcp_listener.py","Receives ASCII → parses → KinesisProducer.send_events()"),
    ("Systemd service","Auto-start","edge/mp91_listener.service","Runs listener on EC2 boot"),
    ("LISTENER FLOW",None,None,None),
    ("Step 1","Accept TCP","socket.accept() on 0.0.0.0:5013",""),
    ("Step 2","Read packet","Read until newline / timeout","ASCII telemetry line from MP91"),
    ("Step 3","Parse fields","lat, lon, speed, ignition, timestamp, device_id",""),
    ("Step 4","Build envelope","{'device_id':..., 'lat':..., 'lon':..., 'speed':..., 'ts':...}",""),
    ("Step 5","Send to Kinesis","KinesisProducer.send_events([event])","partition_key = device_id"),
    ("TRACCAR ALTERNATIVE",None,None,None),
    ("Traccar","Open-source GPS server","docker run -d -p 5013:5013 traccar/traccar","Device type = GT06, port 5013"),
    ("Output","","Outputs to MySQL / H2 DB","Can replace custom TCP listener if preferred"),
]
r=3
for phase,action,detail,note in mp91_rows:
    if action is None: sec(ws,r,1,f"── {phase} ──",span=4)
    else:
        body(ws,r,1,phase,bold=True); body(ws,r,2,action)
        body(ws,r,3,detail,mono=True); body(ws,r,4,note)
    rh(ws,r,22 if detail and len(str(detail))>40 else 18); r+=1

# ── TAB 9: Git Commands ──────────────────────────────────────────────────
ws = wb.create_sheet("Git Commands"); ws.sheet_view.showGridLines = False
make_title(ws, "Git Commands — Run by Ajith (Claude never commits)")
ws.merge_cells("A2:D2")
warn(ws,2,1,"🔒  RULE: Claude never runs git commit or git push. All commits are executed manually by Ajith.",4)
rh(ws,2,24)

for col,(txt,w) in enumerate([("Step",6),("Action",26),("Command",65),("Notes",38)],1):
    hdr(ws,3,col,txt,w); rh(ws,3,22)

git_rows = [
    ("INITIAL COMMIT — M2-M13 + Stage 1 Terraform",None,None,None),
    ("1","Go to repo root",r"cd C:\Users\Laptop\Documents\workspace\industrial-ai-platform-aws",""),
    ("2","Check status","git status","Review all new/modified files"),
    ("3","Stage all","git add -A","Adds everything not in .gitignore"),
    ("4","Review staged diff","git diff --staged --stat","Confirm only expected files staged"),
    ("5","Commit","git commit -m \"feat: M2-M13 AWS platform + Stage 1 Terraform (Kinesis/S3/DDB/IAM)\"","Conventional commits format"),
    ("6","Push","git push origin main","Or your branch name"),
    ("SAFETY CHECKS — run BEFORE commit",None,None,None),
    ("V1","No secrets staged","git diff --staged | grep -i secret","Should return nothing"),
    ("V2","backend.hcl not staged","git diff --staged | grep backend.hcl","Should return nothing — it's .gitignore'd"),
    ("V3","terraform.tfvars not staged","git diff --staged | grep terraform.tfvars","Should return nothing"),
    ("V4","No .tfstate staged","git diff --staged | grep .tfstate","Should return nothing"),
    ("V5","No AWS key IDs staged","git diff --staged | grep -i AKIA","Should return nothing"),
    ("INSPECTION COMMANDS",None,None,None),
    ("I1","Recent commits","git log --oneline -10",""),
    ("I2","Last commit contents","git show --stat HEAD",""),
    ("I3","Untracked files","git ls-files --others --exclude-standard",""),
    ("I4","Remote","git remote -v","Confirm correct GitHub repo"),
    ("WHAT TO COMMIT",None,None,None),
    ("✅","src/","All Python source code (M2: storage/kinesis/checkpoint)",""),
    ("✅","tests/","All moto + unit tests",""),
    ("✅","terraform/","All .tf files (modules + dev-stage1, bootstrap)",""),
    ("✅","docs/","All markdown docs (AWS parity, runbooks)",""),
    ("✅",".github/workflows/","CI/CD YAML pipelines",""),
    ("✅","edge/","Simulator + future TCP listener",""),
    ("❌","backend.hcl","Contains account-specific bucket name","In .gitignore"),
    ("❌","terraform.tfvars","Contains account-specific values","In .gitignore"),
    ("❌","*.tfstate / .terraform/","Terraform state and cache","In .gitignore"),
    ("❌","*.pyc / __pycache__/","Python bytecode","In .gitignore"),
]
r=4
for num,action,cmd,note in git_rows:
    if action is None: sec(ws,r,1,f"── {num} ──",span=4)
    else:
        mono = action in ("","") or num in ("V1","V2","V3","V4","V5","I1","I2","I3","I4")
        body(ws,r,1,num,bold=True); body(ws,r,2,action)
        body(ws,r,3,cmd,mono=True); body(ws,r,4,note)
    rh(ws,r,20); r+=1

out = r"C:\Users\Laptop\Documents\workspace\industrial-ai-platform-aws\IAP_AWS_Ops_Runbook.xlsx"
wb.save(out)
print("Saved:", out)
