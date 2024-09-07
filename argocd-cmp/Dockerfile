
#: Build Nyl itself.
#: -----------------

FROM python:3.12-slim AS build
WORKDIR /build
RUN pip install uv==0.4.7
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv venv /opt/nyl
RUN --mount=type=cache,target=/tmp/uv-cache \
    uv export > requirements.txt \
    && uv pip install --cache-dir /tmp/uv-cache --link-mode=copy --python=/opt/nyl --requirement=requirements.txt \
    && /opt/nyl/bin/nyl version

#: Base stage in which we'll fetch binaries from third-party tools.
#: ----------------------------------------------------------------

FROM alpine AS fetch-bin-base
RUN apk add bash curl openssl upx
RUN \
    case "$(uname -m)" in \
        x86_64) BIN_ARCH='amd64' ;; \
        aarch64) BIN_ARCH='arm64' ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac \
    && printf "%s" "$BIN_ARCH" > /BINARY_ARCH


#: Fetch binaries for ArgoCD, Helm and SOPS.
#: -----------------------------------------

FROM fetch-bin-base AS argocd-bin
# Find ArgoCD releases at https://github.com/argoproj/argo-cd/releases
ARG ARGOCD_VERSION=v2.12.0
RUN curl -sSfLo /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-$(cat /BINARY_ARCH) \
    && chmod +x /usr/local/bin/argocd \
    && upx /usr/local/bin/argocd \
    && argocd version --client

FROM fetch-bin-base AS helm-bin
# Find Helm releases at https://github.com/helm/helm/releases
ARG HELM_VERSION=v3.15.3
RUN curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
    && chmod 700 get_helm.sh \
    && ./get_helm.sh --version $HELM_VERSION \
    && upx /usr/local/bin/helm \
    && helm version

FROM fetch-bin-base AS sops-bin
# Find SOPS releases at https://github.com/getsops/sops/releases
ARG SOPS_VERSION=v3.9.0
RUN curl -LO https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.$(cat /BINARY_ARCH) \
    && mv sops-${SOPS_VERSION}.linux.$(cat /BINARY_ARCH) /usr/local/bin/sops \
    && chmod +x /usr/local/bin/sops \
    && upx /usr/local/bin/sops \
    && sops --version


#: Build the ArgoCD CMP server image.
#: ----------------------------------

FROM python:3.12-slim AS nyl-cmp

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=argocd-bin /usr/local/bin/argocd /usr/local/bin/argocd
RUN ln -s /usr/local/bin/argocd /usr/local/bin/argocd-cmp-server && chown 999:999 /usr/local/bin/argocd-cmp-server
COPY --from=helm-bin /usr/local/bin/helm /usr/local/bin/helm
COPY --from=sops-bin /usr/local/bin/sops /usr/local/bin/sops
COPY --from=build /opt/nyl /opt/nyl
COPY --chown=999 argocd-cmp/plugin.yaml /home/argocd/cmp-server/config/plugin.yaml
ENV PATH="${PATH}:/opt/nyl/bin"
RUN useradd -u 999 -m argocd
USER argocd
WORKDIR /home/argocd
VOLUME /home/argocd/cmp-server/plugins/
ENTRYPOINT [ "/usr/local/bin/argocd-cmp-server" ]
