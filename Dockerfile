# syntax=docker/dockerfile:1.7
# Portable OpenCascade/CadQuery runtime for the CAD defeaturing CLI.
# GPU support is optional; the core CLI is CPU/OpenCascade based.
FROM mambaorg/micromamba:1.5.10-jammy

USER root
WORKDIR /app

COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml
RUN micromamba create --yes --file /tmp/environment.yml --name cad-defeature \
    && micromamba clean --all --yes

COPY --chown=$MAMBA_USER:$MAMBA_USER pyproject.toml README.md ./
COPY --chown=$MAMBA_USER:$MAMBA_USER src ./src
COPY --chown=$MAMBA_USER:$MAMBA_USER policies ./policies

RUN micromamba run --name cad-defeature python -m pip install --no-cache-dir . \
    && mkdir -p /workspace/input /workspace/output /workspace/reports \
    && chown -R $MAMBA_USER:$MAMBA_USER /app /workspace

USER $MAMBA_USER
ENV PATH=/opt/conda/envs/cad-defeature/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace
ENTRYPOINT ["micromamba", "run", "--no-capture-output", "--name", "cad-defeature", "cad-defeature"]
CMD ["--help"]
