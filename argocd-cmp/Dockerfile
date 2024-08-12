
#: Build Nyl itself.
#: -----------------

FROM python:3.12-slim AS build
WORKDIR /build
RUN pip install pdm uv
COPY pyproject.toml pdm.lock pdm.toml README.md ./
COPY src/ src/
RUN pdm export > requirements.txt
RUN uv venv /opt/nyl
RUN uv pip install --python /opt/nyl/bin/python -r requirements.txt ./

#: Build the ArgoCD CMP server image.
#: ----------------------------------

FROM alpine/curl AS argocd-bin
ARG ARGOCD_VERSION=v2.12.0
RUN \
    case "$(uname -m)" in \
        x86_64) BIN_ARCH='amd64' ;; \
        aarch64) BIN_ARCH='arm64' ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    curl -sSfLo /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-${BIN_ARCH} \
    && chmod +x /usr/local/bin/argocd

FROM python:3.12-slim AS nyl-cmp
COPY --from=argocd-bin /usr/local/bin/argocd /usr/local/bin/argocd-cmp-server
COPY --from=build /opt/nyl /opt/nyl
COPY argocd-cmp/plugin.yaml /home/argocd/cmp-server/config/plugin.yaml
ENV PATH="${PATH}:/opt/nyl/bin"
ENTRYPOINT [ "/usr/local/bin/argocd-cmp-server" ]
