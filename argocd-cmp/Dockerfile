
#: Build Nyl itself.
#: -----------------

FROM python:3.13-alpine AS build
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /bin/uv

WORKDIR /opt/nyl

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --link-mode=copy --compile-bytecode

ADD src /opt/nyl
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --frozen --link-mode=copy --compile-bytecode

#: Base stage in which we'll fetch binaries from third-party tools.
#: ----------------------------------------------------------------

FROM alpine AS fetch-bin-base
RUN apk add bash curl openssl upx
RUN \
    case "$(uname -m)" in \
        x86_64) BIN_ARCH='amd64' ;; \
        aarch64) BIN_ARCH='arm64' ;; \
        *) echo "Unsupported architecture: $(uname -m)" && exit 1 ;; \
    esac \
    && printf "%s" "$BIN_ARCH" > /BINARY_ARCH


#: Fetch binaries for ArgoCD, Helm and SOPS.
#: -----------------------------------------

FROM fetch-bin-base AS argocd-bin
# Find ArgoCD releases at https://github.com/argoproj/argo-cd/releases
# renovate: datasource=github-releases depName=argocd packageName=argoproj/argo-cd
ARG ARGOCD_VERSION=v2.14.11
RUN curl -sSfLo /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-$(cat /BINARY_ARCH) \
    && chmod +x /usr/local/bin/argocd \
    && upx /usr/local/bin/argocd \
    && argocd version --client

FROM fetch-bin-base AS helm-bin
# Find Helm releases at https://github.com/helm/helm/releases
# renovate: datasource=github-releases depName=helm packageName=helm/helm
ARG HELM_VERSION=v3.17.3
RUN curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
    && chmod 700 get_helm.sh \
    && ./get_helm.sh --version $HELM_VERSION \
    && upx /usr/local/bin/helm \
    && helm version

FROM fetch-bin-base AS sops-bin
# Find SOPS releases at https://github.com/getsops/sops/releases
# renovate: datasource=github-releases depName=sops packageName=getsops/sops
ARG SOPS_VERSION=v3.10.2
RUN curl -fLO https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.$(cat /BINARY_ARCH) \
    && mv sops-${SOPS_VERSION}.linux.$(cat /BINARY_ARCH) /usr/local/bin/sops \
    && chmod +x /usr/local/bin/sops \
    && upx /usr/local/bin/sops \
    && sops --version

FROM fetch-bin-base AS kyverno-bin
# renovate: datasource=github-releases depName=kyverno packageName=kyverno/kyverno
ARG KYVERNO_VERSION=1.14.1
RUN \
    case "$(uname -m)" in \
        x86_64) KYVERNO_ARCH='x86_64' ;; \
        aarch64) KYVERNO_ARCH='arm64' ;; \
        *) echo "Unsupported architecture: $(uname -m)" && exit 1 ;; \
    esac \
    && curl -fLO https://github.com/kyverno/kyverno/releases/download/v${KYVERNO_VERSION}/kyverno-cli_v${KYVERNO_VERSION}_linux_${KYVERNO_ARCH}.tar.gz \
    && tar -xvf kyverno-cli_v${KYVERNO_VERSION}_linux_${KYVERNO_ARCH}.tar.gz \
    && mv kyverno /usr/local/bin/ \
    && upx /usr/local/bin/kyverno

#: Build the ArgoCD CMP server image.
#: ----------------------------------

FROM python:3.13-alpine AS nyl-cmp
RUN apk add git
COPY --from=argocd-bin /usr/local/bin/argocd /usr/local/bin/argocd
RUN ln -s /usr/local/bin/argocd /usr/local/bin/argocd-cmp-server && chown 999:999 /usr/local/bin/argocd-cmp-server
COPY --from=helm-bin /usr/local/bin/helm /usr/local/bin/helm
COPY --from=sops-bin /usr/local/bin/sops /usr/local/bin/sops
COPY --from=kyverno-bin /usr/local/bin/kyverno /usr/local/bin/kyverno
COPY --from=build /opt/nyl /opt/nyl
RUN ln -s /opt/nyl/.venv/bin/nyl /usr/local/bin/nyl
RUN ln -s /opt/nyl/.venv/bin/nyl-daemon /usr/local/bin/nyl-daemon
COPY --chown=999 argocd-cmp/plugin.yaml /home/argocd/cmp-server/config/plugin.yaml

# Validate Nyl can be run, plus various setup steps.
RUN nyl version \
    && addgroup -S argocd \
    && adduser -u 999 argocd -G argocd -D \
    && mkdir -p /var/log/nyl \
    && chown -R argocd:argocd /var/log/nyl

USER argocd
WORKDIR /home/argocd
VOLUME /home/argocd/cmp-server/plugins/
ENTRYPOINT [ "/usr/local/bin/argocd-cmp-server" ]
