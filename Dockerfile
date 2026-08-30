FROM python:3.13

WORKDIR /streamlit

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh","-c","streamlit run streamlit.py --server.port=$PORT --server.address=0.0.0.0"]
