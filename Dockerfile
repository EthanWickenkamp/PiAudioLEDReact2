FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PULSE_RUNTIME_PATH=/run/pulse

# Install audio + bluetooth dependencies
RUN apt-get update && apt-get install -y \
    pulseaudio \
    pulseaudio-module-bluetooth \
    bluez \
    alsa-utils \
    dbus \
    udev \
    libasound2 \
    python3-dbus \
    && apt-get clean

# App files
WORKDIR /app
COPY app/ /app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]