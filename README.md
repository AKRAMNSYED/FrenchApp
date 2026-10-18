# French Website

A Streamlit-powered French vocabulary notebook with English–French translation, bilingual sentence examples, searchable vocabulary, custom 10-word quizzes, and colorful learning milestone badges.

Vocabulary and earned badges are stored locally in JSON files and excluded from Git so your personal learning data stays private.

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

The JSON files are created automatically when needed. Keep them in this folder to retain your local collection and badges.