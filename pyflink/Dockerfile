FROM flink:1.19.1-scala_2.12

# Minimal Phase A image: add Python runtime for future PyFlink jobs.
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Helpful defaults for PyFlink execution in later phases.
ENV PYFLINK_CLIENT_EXECUTABLE=python3
ENV PYFLINK_PYTHON=python3

WORKDIR /opt/flink
