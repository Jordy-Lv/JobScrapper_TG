import os

# Las pruebas usan solo config.yaml, aunque el PC tenga un config.local.yaml
os.environ["BUSCADOR_SIN_CONFIG_LOCAL"] = "1"
