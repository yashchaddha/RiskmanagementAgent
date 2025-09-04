AWS='aws --region us-east-1'

yum install -y gettext jq

IMAGE=$($AWS ecr describe-images \
	--repository-name complynexus-agentic \
	--query 'sort_by(imageDetails,& imagePushedAt)[-1]')
export BUILD=$(echo $IMAGE | jq -r '.imageTags[0]')
echo 'Build:' $BUILD

envsubst < task.base.json > task.json

$AWS ecs deploy \
	--cluster CNBase-ClusterEB0386A7-G4PWFAYczwPu \
	--service arn:aws:ecs:us-east-1:760974246385:service/CNBase-ClusterEB0386A7-G4PWFAYczwPu/CNAgenticAppProd-ServiceD69D759B-LvqYhu8exbng \
	--task-definition task.json \
	--codedeploy-appspec appspec.base.yaml \
	--codedeploy-application CNAgenticAppProd-ApplicationD9CED6CE-OmxGSwP5YfAt \
	--codedeploy-deployment-group DgpECS-CNAgenticAppProd
