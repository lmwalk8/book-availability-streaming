FROM flink:1.19.1-scala_2.12

# Full JDK is required so pemja (PyFlink dependency) can find JAVA_HOME/include.
# The base image's /opt/java/openjdk is JRE-like and lacks headers.
ARG TARGETARCH
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
      openjdk-17-jdk \
      python3 \
      python3-pip \
      python3-dev \
      curl \
      ca-certificates \
      g++ && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# Debian JDK path is arch-specific (amd64 / arm64).
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-${TARGETARCH}
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV PYFLINK_CLIENT_EXECUTABLE=python3
ENV PYFLINK_PYTHON=python3

WORKDIR /opt/flink

# Verify JDK headers exist before compiling pemja.
RUN test -d "${JAVA_HOME}/include" && javac -version

# Install PyFlink matching this image version (1.19.1).
COPY requirements.txt /opt/flink/requirements-pyflink.txt
RUN pip3 install --no-cache-dir -r /opt/flink/requirements-pyflink.txt

# Kafka SQL connector for Flink 1.19 (used by PyFlink Kafka source / Table API).
ARG KAFKA_CONNECTOR_VERSION=3.2.0-1.19
RUN curl -fsSL \
      "https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/${KAFKA_CONNECTOR_VERSION}/flink-sql-connector-kafka-${KAFKA_CONNECTOR_VERSION}.jar" \
      -o "/opt/flink/lib/flink-sql-connector-kafka-${KAFKA_CONNECTOR_VERSION}.jar"

# Flink JDBC connector (JdbcSink / JdbcConnectionOptions) for Flink 1.19.
ARG JDBC_CONNECTOR_VERSION=3.2.0-1.19
RUN curl -fsSL \
      "https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-jdbc/${JDBC_CONNECTOR_VERSION}/flink-connector-jdbc-${JDBC_CONNECTOR_VERSION}.jar" \
      -o "/opt/flink/lib/flink-connector-jdbc-${JDBC_CONNECTOR_VERSION}.jar"

# PostgreSQL JDBC driver (org.postgresql.Driver)
ARG POSTGRES_JDBC_VERSION=42.7.4
RUN curl -fsSL \
      "https://repo.maven.apache.org/maven2/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar" \
      -o "/opt/flink/lib/postgresql-${POSTGRES_JDBC_VERSION}.jar"

# Job sources (parse/hash/postgres-sink).
COPY jobs/ /opt/flink/usrlib/jobs/
ENV PYTHONPATH=/opt/flink/usrlib/jobs
