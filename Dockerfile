
#: Build Nyl itself.
#: -----------------

FROM python:3.12 AS build
WORKDIR /build
RUN pip install pex
COPY pyproject.toml README.md ./
COPY src/ src/
RUN ls -lha && pex -v -o /usr/local/bin/nyl ./ -c nyl --resolver-version=pip-2020-resolver

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

FROM python:3.12 AS nyl-cmp
COPY --from=argocd-bin /usr/local/bin/argocd /usr/local/bin/argocd-cmp-server
COPY --from=build /usr/local/bin/nyl /usr/local/bin/nyl
ENTRYPOINT [ "/usr/local/bin/arogcd-cmp-server" ]
