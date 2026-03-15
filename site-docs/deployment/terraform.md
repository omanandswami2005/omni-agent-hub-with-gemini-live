# Terraform Deployment

Omni includes Terraform configuration for automated GCP infrastructure provisioning.

## Setup

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your GCP project details
```

## Apply

```bash
terraform init
terraform plan
terraform apply
```

## Resources Provisioned

- Cloud Run service for the backend
- Firestore database
- Firebase Hosting for the dashboard
- IAM service accounts and roles
- Artifact Registry for container images

## Configuration

See `deploy/terraform/variables.tf` for all configurable variables.
