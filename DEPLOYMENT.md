# Deployment notes

## Streamlit Community Cloud
1. Push this project to a GitHub repository.
2. In Streamlit Community Cloud, create an app from that repository.
3. Select `app.py` as the main file.
4. Deploy. The bundled CSV is read from `data/IRFC_BSE_Data.csv`.

No API key is needed to run the dashboard. If you later add a live API feature, store credentials in the deployment platform's secrets manager and never in source code.
