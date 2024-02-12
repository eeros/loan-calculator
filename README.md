# loan-calculator

Loan calculator mock is rest-based calculator engine which calculates different loan-related calculations through REST API.

Running example: https://calculator-phis5bgl7q-lz.a.run.app/docs

How to get this run on Goodle Cloud:

1. BUiLD

  docker build -t gcr.io/calculation-engine-413107/calculator .

2. PUSH

 docker push gcr.io/<project-id></project-id>/calculator

3. DEPLOY
   
gcloud run deploy --image gcr.io/<project-id>/calculator --platform managed
