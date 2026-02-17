from src.hagiographies_import.model import *
from src.hagiographies_import.db import engine
from sqlalchemy_data_model_visualizer import generate_data_model_diagram, add_web_font_and_interactivity
import os

models = [EditionManuscriptLink, Origin, Text, City, Library, Location, Manuscript, Provenance, Witness, Reference, Edition]
output_file_name = '../data/hagiographies_model'
try:
    generate_data_model_diagram(models, output_file_name)
    os.remove(output_file_name)
except FileNotFoundError:
    print("Ignored xdg-open error")