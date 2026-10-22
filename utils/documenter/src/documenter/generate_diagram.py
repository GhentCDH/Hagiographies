from sqlmodel import SQLModel
import utilities.model  # noqa: F401  (registers every table model)
from sqlalchemy_data_model_visualizer import generate_data_model_diagram
import os

def main():
    # Every table model in utilities.model, so new tables appear without
    # editing this list.
    models = sorted(
        (
            mapper.class_
            for mapper in SQLModel._sa_registry.mappers
            if mapper.class_.__module__ == "utilities.model"
        ),
        key=lambda cls: cls.__tablename__,
    )
    output_file_name = '../../data/hagiographies_model'
    try:
        generate_data_model_diagram(models, output_file_name)
        os.remove(output_file_name)
    except FileNotFoundError:
        print("Ignored xdg-open error")

if __name__ == "__main__":
    main()
