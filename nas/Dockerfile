FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
WORKDIR /app
COPY experiments/supplied-v2/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY experiments/supplied-v2/collector.py /app/experiments/supplied-v2/collector.py
COPY nas/run.py nas/web.py /app/nas/
COPY nas/static /app/nas/static
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER pwuser
EXPOSE 8899
ENTRYPOINT ["python"]
CMD ["/app/nas/web.py"]
