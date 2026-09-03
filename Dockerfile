FROM python:3.13

WORKDIR /streamlit

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /streamlit
USER appuser

CMD ["sh", "-c", "streamlit run streamlit.py --server.address=0.0.0.0 --server.port=${PORT:-8502} --server.fileWatcherType=none"]