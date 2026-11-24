##############################################################################
# Edge Server module — EC2 t4g.nano (ARM/Graviton) running the MP91 TCP listener
#
# COST (ca-central-1, approx): t4g.nano ~$3.40/mo + public IPv4 ~$3.65/mo
#   + 8GB gp3 ~$0.70/mo  =>  ~$8/mo running 24/7, ~$4.40/mo while stopped.
#
# STABLE IP: the EIP is a separate resource with prevent_destroy. Changing
# user_data replaces ONLY the instance; the EIP re-associates, IP unchanged.
# Never run `terraform destroy -target=module.edge_server` — stop the
# instance instead (aws ec2 stop-instances).
#
# What this creates:
#   - EC2 instance (t3.micro, Amazon Linux 2023) in ca-central-1
#   - Security group: inbound TCP 5013 (MP91), SSH 22 (your IP), outbound all
#   - IAM role + instance profile: S3 PutObject to the lake bucket
#   - Elastic IP so the public IP is stable (device SMS config won't change)
#   - CloudWatch log group for listener stdout
#   - User data script: installs Python 3.12, copies listener, systemd service
#
# After terraform apply, read the output edge_server_public_ip and use it in
# the Mictrack Config Tool:
#   Server : <edge_server_public_ip>
#   Port   : 5013
#   APN    : mobile.mictrack.com
##############################################################################

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-kernel-*-arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── IAM ───────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "edge_server" {
  name = "${var.name_prefix}-edge-server-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "edge_server_s3" {
  name = "${var.name_prefix}-edge-server-s3"
  role = aws_iam_role.edge_server.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3LakeBucketWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          var.lake_bucket_arn,
          "${var.lake_bucket_arn}/*",
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "arn:aws:logs:${var.region}:*:log-group:/iap/edge-server:*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "edge_server_ssm" {
  role       = aws_iam_role.edge_server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "edge_server" {
  name = "${var.name_prefix}-edge-server-profile"
  role = aws_iam_role.edge_server.name
  tags = var.tags
}

# ── Security Group ────────────────────────────────────────────────────────────

resource "aws_security_group" "edge_server" {
  name        = "${var.name_prefix}-edge-server-sg"
  description = "MP91 TCP listener: allow 5013 from anywhere, SSH from admin IP"
  vpc_id      = var.vpc_id

  # MP91 devices connect from any cellular IP
  ingress {
    description = "MP91 TCP telemetry"
    from_port   = 5013
    to_port     = 5013
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH — restrict to your IP in tfvars (leave empty to disable)
  dynamic "ingress" {
    for_each = length(var.ssh_allowed_cidrs) > 0 ? [1] : []
    content {
      description = "SSH admin access"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = var.ssh_allowed_cidrs
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-edge-server-sg" })
}

# ── Elastic IP (stable public IP for device SMS config) ───────────────────────

resource "aws_eip" "edge_server" {
  domain = "vpc"
  tags   = merge(var.tags, { Name = "${var.name_prefix}-edge-server-eip" })

  # The MP91 is configured with this IP by Mictrack support. Losing it means
  # another support round-trip. Remove this block only to retire the device.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_eip_association" "edge_server" {
  instance_id   = aws_instance.edge_server.id
  allocation_id = aws_eip.edge_server.id
}

# ── CloudWatch Log Group ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "edge_server" {
  name              = "/iap/edge-server"
  retention_in_days = 14
  tags              = var.tags
}

# ── EC2 Instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "edge_server" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = "t4g.nano"
  iam_instance_profile   = aws_iam_instance_profile.edge_server.name
  vpc_security_group_ids = [aws_security_group.edge_server.id]
  subnet_id              = var.subnet_id

  # Store the key pair name in tfvars — leave blank to disable SSH
  key_name = var.key_pair_name != "" ? var.key_pair_name : null

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    lake_bucket = var.lake_bucket
    region      = var.region
    tcp_port    = 5013
  }))

  # Script changes replace the instance (bootstrap only runs on first boot).
  user_data_replace_on_change = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-edge-server" })

  lifecycle {
    # Don't replace instance if AMI updates — use SSM patch manager instead
    ignore_changes = [ami]
  }
}
