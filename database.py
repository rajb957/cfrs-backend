from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv
load_dotenv()

# SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://postgres:NnsjgtirQLoVxhqOyEGkDBpoAxKDZGgL@autorack.proxy.rlwy.net:29627/railway"
SQLALCHEMY_DATABASE_URL = os.environ.get('DATABASE_URL')
SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# Create a connection to the database

engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create a Session class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a base class
Base = declarative_base()