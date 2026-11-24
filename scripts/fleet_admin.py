"""FleetPilot admin CLI — create accounts, register vehicles/devices, link logins.

Until there is an admin UI, onboarding a customer is three commands:

  python scripts/fleet_admin.py add-account  --account ajith --name "Ajith Kumara" --kind personal
  python scripts/fleet_admin.py add-vehicle  --account ajith --vehicle car1 --name "My car" --device 7018532019 [--plate ABC123] [--driver "Ajith"]
  python scripts/fleet_admin.py link-user    --account ajith --email aakumara@gmail.com [--create]
  python scripts/fleet_admin.py list
  python scripts/fleet_admin.py refresh      # rebuild every account's dashboard data now

Uses your AWS profile (set $env:AWS_PROFILE = "iap-dev"). --create on link-user creates the
Cognito login and emails a temporary password.
"""
import argparse
import json
import boto3

REGION = "ca-central-1"
TABLE = "iap-dev-fleet"
POOL_NAME = "iap-dev-track"
PROCESS_FN = "iap-dev-mp91-process"

ddb = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)


def pool_id():
    idp = boto3.client("cognito-idp", region_name=REGION)
    for p in idp.list_user_pools(MaxResults=60)["UserPools"]:
        if p["Name"] == POOL_NAME:
            return idp, p["Id"]
    raise SystemExit(f"Cognito pool {POOL_NAME} not found")


def add_account(a):
    ddb.put_item(Item={"PK": f"ACCOUNT#{a.account}", "SK": "META", "name": a.name, "kind": a.kind, "plan": a.plan})
    print(f"account {a.account} ({a.kind}) saved")


def add_vehicle(a):
    if not ddb.get_item(Key={"PK": f"ACCOUNT#{a.account}", "SK": "META"}).get("Item"):
        raise SystemExit(f"account {a.account} does not exist; run add-account first")
    owner = ddb.get_item(Key={"PK": f"DEVICE#{a.device}", "SK": "META"}).get("Item")
    if owner and (owner["account_id"], owner["vehicle_id"]) != (a.account, a.vehicle):
        raise SystemExit(f"device {a.device} already belongs to {owner['account_id']}/{owner['vehicle_id']}")
    item = {"PK": f"ACCOUNT#{a.account}", "SK": f"VEHICLE#{a.vehicle}", "name": a.name, "device_id": a.device}
    if a.plate:
        item["plate"] = a.plate
    if a.driver:
        item["driver"] = a.driver
    ddb.put_item(Item=item)
    ddb.put_item(Item={"PK": f"DEVICE#{a.device}", "SK": "META", "account_id": a.account, "vehicle_id": a.vehicle})
    print(f"vehicle {a.vehicle} ({a.name}) with device {a.device} -> account {a.account}")


def link_user(a):
    idp, pid = pool_id()
    if a.create:
        idp.admin_create_user(UserPoolId=pid, Username=a.email, DesiredDeliveryMediums=["EMAIL"],
                              UserAttributes=[{"Name": "email", "Value": a.email},
                                              {"Name": "email_verified", "Value": "true"}])
        print(f"login created for {a.email}; temporary password emailed")
    u = idp.admin_get_user(UserPoolId=pid, Username=a.email)
    sub = next(x["Value"] for x in u["UserAttributes"] if x["Name"] == "sub")
    ddb.put_item(Item={"PK": f"USER#{sub}", "SK": "META", "account_id": a.account, "email": a.email, "role": a.role})
    print(f"{a.email} -> account {a.account} ({a.role})")


def list_all(_):
    for it in sorted(ddb.scan()["Items"], key=lambda i: (i["PK"], i["SK"])):
        print(json.dumps(it, default=str))


def refresh(_):
    r = boto3.client("lambda", region_name=REGION).invoke(FunctionName=PROCESS_FN, Payload=json.dumps({"force": True}))
    print(r["Payload"].read().decode())


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sp = p.add_subparsers(dest="cmd", required=True)
x = sp.add_parser("add-account"); x.add_argument("--account", required=True); x.add_argument("--name", required=True)
x.add_argument("--kind", choices=["fleet", "personal"], default="fleet"); x.add_argument("--plan", default="starter"); x.set_defaults(fn=add_account)
x = sp.add_parser("add-vehicle"); x.add_argument("--account", required=True); x.add_argument("--vehicle", required=True)
x.add_argument("--name", required=True); x.add_argument("--device", required=True); x.add_argument("--plate"); x.add_argument("--driver"); x.set_defaults(fn=add_vehicle)
x = sp.add_parser("link-user"); x.add_argument("--account", required=True); x.add_argument("--email", required=True)
x.add_argument("--role", default="owner"); x.add_argument("--create", action="store_true"); x.set_defaults(fn=link_user)
sp.add_parser("list").set_defaults(fn=list_all)
sp.add_parser("refresh").set_defaults(fn=refresh)

if __name__ == "__main__":
    args = p.parse_args()
    args.fn(args)
