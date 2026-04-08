cd /workspaces/aws-reconciliation-engine && rm -rf package deployment.zip && mkdir package
pip install -r requirements.txt --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: --target ./package
cp -r src ./package/ && cd package && zip -r9 ../deployment.zip . && cd ..
aws lambda update-function-code --function-name payment-reconciliation --zip-file fileb:///workspaces/aws-reconciliation-engine/deployment.zip --region ap-south-1
aws lambda update-function-code --function-name sqs_lambda --zip-file fileb:///workspaces/aws-reconciliation-engine/deployment.zip --region ap-south-1

