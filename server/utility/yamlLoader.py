import yaml

class LoadYaml:
    def __init__(self, file_path="settings.yaml"):
        self.config = self._load_yaml(file_path)

    @staticmethod
    def _load_yaml(file_path):
        with open(file_path, "r") as file:
            return yaml.safe_load(file) or {}

    def get(self, key, default=None):
        """
        Fetch a top-level key from the YAML.
        """
        return self.config.get(key, default)

    def get_nested(self, *keys, default=None):
        """
        Fetch nested keys safely.
        """
        data = self.config
        try:
            for key in keys:
                data = data[key]
            return data
        except (KeyError, TypeError):
            return default

