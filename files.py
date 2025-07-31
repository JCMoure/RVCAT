from pathlib      import Path
import importlib.resources, json, os

PROCESSOR_PATH = importlib.resources.files("rvcat").joinpath("processors")
PROGRAM_PATH   = importlib.resources.files("rvcat").joinpath("examples")


# Load JSON file
def load_json(name, proc=True) -> json:

    if proc:
      json_path = PROCESSOR_PATH + name
    else:
      json_path = PROGRAM_PATH + name

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"File not found: {json_path}")

    # Attempt to open the file
    try:
        with open(json_path, "r") as f:
           proc = json.load(f)
           if isinstance(proc, str):  # if data is a string, convert to JSON structure
              try:
                cfg = json.loads(proc)
              except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
           else:
              cfg = proc

        return cfg

    except FileNotFoundError as e:
           print(f"Error: {e}")
    except IOError as e:
           print(f"I/O Error while opening file: {e}")
    except Exception as e:
           print(f"Unexpected error: {e}")


# return JSON structure containing names of programs found in PROGRAM_PATH
def list_json(proc=True) -> str:
  
    if proc:
        l = [f.split('.')[:-1] for f in os.listdir(PROCESSOR_PATH) if (f.endswith(".json"))]
    else:
        l = ['.'.join(f.split('.')[:-1]) for f in os.listdir(PROGRAM_PATH) if f.endswith(".json")]

    return json.dumps(l)


# write json to disk
def export_json(data, name, proc=True):

    if isinstance(data, str):  # if data is a string, convert to JSON structure
        try:
            cfg = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    else:
        cfg = data

    #  os.path.splitext(os.path.basename(self.name))[0]


    if proc:
        out_path: Path = PROCESSOR_PATH.joinpath(f"{name}.json")
    else:
        out_path: Path = PROGRAM_PATH.joinpath(f"{name}.json")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    cfg['name'] = name

    with open(out_path, "w") as f:
        json.dump(cfg, f, indent=2)
