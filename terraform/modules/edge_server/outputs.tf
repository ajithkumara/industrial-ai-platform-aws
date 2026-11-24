output "public_ip" {
  description = "Elastic IP — use this as the Server address in Mictrack Config Tool"
  value       = aws_eip.edge_server.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.edge_server.id
}

output "role_name" {
  description = "Instance role name (the root module attaches the live-position DynamoDB policy to it)"
  value       = aws_iam_role.edge_server.name
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.edge_server.id
}

output "tcp_endpoint" {
  description = "Full TCP endpoint string for device config (Server:Port)"
  value       = "${aws_eip.edge_server.public_ip}:5013"
}

output "alarm_topic_arn" {
  description = "SNS topic for edge-server alarms (Phase 2 monitoring reuses it)"
  value       = aws_sns_topic.edge_alarms.arn
}
