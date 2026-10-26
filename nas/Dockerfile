FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb fluxbox x11vnc novnc websockify fonts-nanum \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir /opt/whoga-novnc && cp -RL /usr/share/novnc/core /usr/share/novnc/vendor /opt/whoga-novnc/
WORKDIR /app
COPY experiments/supplied-v2/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY experiments/supplied-v2/collector.py /app/experiments/supplied-v2/collector.py
COPY nas/telegram_setup.py nas/plan.py nas/run.py nas/web.py nas/desktop.py nas/entrypoint.py nas/diagnostics.py nas/resources.py nas/comparison.py nas/browser_control.py nas/browser_runtime.py nas/version.py nas/source-version.json /app/nas/
COPY nas/static /app/nas/static
ARG VCS_REF=unknown
RUN python /app/nas/version.py --write-build-info "$VCS_REF"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DISPLAY=:99 \
    XDG_CONFIG_HOME=/tmp/whoga-xdg XDG_CACHE_HOME=/tmp/whoga-cache WHOGA_NOVNC_ROOT=/opt/whoga-novnc
RUN mkdir -p /config /output && chown -R pwuser:pwuser /config /output
USER pwuser
EXPOSE 8899
ENTRYPOINT ["python"]
CMD ["/app/nas/entrypoint.py"]
