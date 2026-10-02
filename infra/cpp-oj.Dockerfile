# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016 AS certificates
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS runtime
# Bootstrap HTTPS using the trusted CA bundle from a pinned official image.
COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
ARG DEBIAN_MIRROR=deb.debian.org
RUN case "$DEBIAN_MIRROR" in deb.debian.org|mirror.sjtu.edu.cn) ;; *) exit 2 ;; esac \
    && sed -i "s|http://deb.debian.org|https://${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && rm -f /etc/apt/apt.conf.d/docker-clean \
    && printf 'Acquire::Retries "3"; Acquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80-e2e-network
# Keep downloaded packages across transient network failures; caches are not image layers.
# g++ is required at runtime because this is the real judge, not a Mock.
RUN --mount=type=cache,id=oj-e2e-apt,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=oj-e2e-lists,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends g++ libmysqlcppconn7v5 python3 ca-certificates \
    && groupadd --gid 10001 oj && useradd --uid 10001 --gid oj --no-create-home oj

FROM runtime AS build
RUN --mount=type=cache,id=oj-e2e-apt,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=oj-e2e-lists,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends build-essential cmake libmysqlcppconn-dev libgtest-dev
WORKDIR /source
COPY --from=sut /CMakeLists.txt ./
COPY --from=sut /src ./src
COPY --from=sut /include ./include
COPY --from=sut /tools ./tools
COPY --from=sut /tests ./tests
COPY --from=sut /html ./html
COPY --from=sut /static ./static
# Upstream's post-build copy requires this file; never copy its local credentials.
RUN printf '{}' > config.json \
    && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS=-DCPPHTTPLIB_THREAD_POOL_COUNT=8 \
    && cmake --build build --target cpp-oj --parallel 2

FROM runtime
COPY --from=build /source/build/cpp-oj /opt/oj/cpp-oj
COPY --from=build /source/html /opt/oj/html
COPY --from=build /source/static /opt/oj/static
COPY infra/cpp_oj_entrypoint.py /opt/oj/entrypoint.py
ARG SUT_SHA
LABEL org.opencontainers.image.revision=${SUT_SHA}
USER 10001:10001
WORKDIR /runtime
EXPOSE 8080
ENTRYPOINT ["python3", "/opt/oj/entrypoint.py"]
