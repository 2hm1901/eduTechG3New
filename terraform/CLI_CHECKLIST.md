# Service Verification Checklist (AWS CLI)

> Replace placeholders like <ACCOUNT_ID>, <REGION>, <API_ID>, <CF_DOMAIN> as needed.

## Networking
- [ ] VPC exists
  - `aws ec2 describe-vpcs --filters Name=tag:Name,Values=ai-study-buddy-vpc --region ap-southeast-2`
- [ ] Private subnet exists
  - `aws ec2 describe-subnets --filters Name=tag:Name,Values=ai-study-buddy-private-subnet --region ap-southeast-2`
- [ ] VPC endpoints exist (S3, DynamoDB, Bedrock)
  - `aws ec2 describe-vpc-endpoints --filters Name=vpc-endpoint-type,Values=Gateway,Interface --region ap-southeast-2`

## S3
- [ ] Frontend bucket exists
  - `aws s3api head-bucket --bucket ai-study-buddy-frontend-<894597652722> --region ap-southeast-2`
- [ ] PDF bucket exists
  - `aws s3api head-bucket --bucket ai-study-buddy-pdf-<894597652722> --region ap-southeast-2`
- [ ] PDF bucket encryption enabled
  - `aws s3api get-bucket-encryption --bucket ai-study-buddy-pdf-<894597652722> --region ap-southeast-2`
- [ ] PDF bucket notification for Lambda
  - `aws s3api get-bucket-notification-configuration --bucket ai-study-buddy-pdf-<894597652722> --region ap-southeast-2`

## Cognito
- [ ] User pool exists
  - `aws cognito-idp list-user-pools --max-results 60 --region ap-southeast-2 | grep ai-study-buddy-user-pool`
- [ ] User pool client exists
  - `aws cognito-idp list-user-pool-clients --user-pool-id <USER_POOL_ID> --region ap-southeast-2`

## API Gateway
- [ ] REST API exists
  - `aws apigateway get-rest-apis --region ap-southeast-2 | grep ai-study-buddy-api`
- [ ] Stage exists
  - `aws apigateway get-stages --rest-api-id <API_ID> --region ap-southeast-2`

## Lambda
- [ ] Functions exist
  - `aws lambda list-functions --region ap-southeast-2 | grep ai-study-buddy-`
- [ ] Text extraction has S3 trigger
  - `aws lambda get-policy --function-name ai-study-buddy-text-extraction --region ap-southeast-2`

## IAM
- [ ] Lambda roles exist
  - `aws iam list-roles | grep -E "upload-handler-role|text-extraction-role|chat-role|summarize-quiz-role|dashboard-role"`

## DynamoDB
- [ ] Table exists
  - `aws dynamodb describe-table --table-name ai-study-buddy-main --region ap-southeast-2`

## KMS
- [ ] KMS key exists
  - `aws kms list-aliases --region ap-southeast-2 | grep ai-study-buddy-pdf`

## CloudFront
- [ ] Distribution exists
  - `aws cloudfront list-distributions | grep -i ai-study-buddy`
- [ ] Distribution domain resolves
  - `dig +short <CF_DOMAIN>`

## CloudWatch
- [ ] Lambda log groups exist
  - `aws logs describe-log-groups --log-group-name-prefix /aws/lambda/ai-study-buddy- --region ap-southeast-2`
- [ ] Alarms exist
  - `aws cloudwatch describe-alarms --region ap-southeast-2 | grep ai-study-buddy`
