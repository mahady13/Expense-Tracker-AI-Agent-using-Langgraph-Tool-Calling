FROM python:3.13

WORKDIR /streamlit

COPY . /streamlit

RUN pip install -r requirements.txt

EXPOSE 8502

CMD ["streamlit","run","streamlit.py"]
