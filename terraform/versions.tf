terraform {
  required_version = ">= 1.5"

  backend "s3" {
    bucket       = "ai-study-buddy-tfstate-894597652722"
    key          = "w7-hackathon/terraform.tfstate"
    region       = "ap-southeast-2"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
