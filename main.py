# from typing import Optional
import time
from fastapi import FastAPI, Query, Request, Depends, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import SQLAlchemyError
# from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import models
from sqlalchemy.sql import text
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from database import engine,SessionLocal
# from models import Account

#note: we should use migrations here
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# @app.on_event("startup")
# def startup_populate_db():
#     db = SessionLocal()
#     num_files = db.query(models.Blogs).count()
#     if num_files == 0:
#         films = [
#         {'name': 'Blade Runner', 'director': 'Ridley Scott'},
#         {'name': 'Pulp Fiction', 'director': 'Quentin Tarantino'},
#         {'name': 'Mulholland Drive', 'director': 'David Lynch'},
#         {'name': 'The Godfather', 'director': 'Francis Ford Coppola'},
#         {'name': 'The Big Lebowski', 'director': 'Coen Brothers'},
#         {'name': 'The Shining', 'director': 'Stanley Kubrick'},
#         ]
#         for film in films:
#             db.add(models.Films(**film))
#         db.commit()
#         db.close()
#     else:
#         print(f"Database already populated with {num_files} films")
#         db.close()

def convert_to_map(blogs):
    blog_map = []
    for blog in blogs:
        blog_map.append({})
        blog_map[-1]['id'] = blog.id
        blog_map[-1]['title'] = blog.title
        blog_map[-1]['content'] = blog.content
        blog_map[-1]['authorId'] = blog.authorid
        blog_map[-1]['author'] = blog.author_name
        blog_map[-1]['blog_link'] = blog.blog_link
        # blog_map[-1]['blog_img'] = blog.blog_img
        blog_map[-1]['category'] = blog.topic
    
        # blog_map[-1]['rating'] = blog.rating
    # print(blog_map)
    return blog_map 

@app.get("/", response_class=JSONResponse)
async def read_item(
    request: Request, db: Session = Depends(get_db),page: int = 1
):
    
    # blogs = db.query(models.Blogs).order_by(models.Blogs.rating.desc()).offset((page-1)*10).limit(10).all()
    # Write a query to get 10 blogs with author name included
    query = "SELECT blog_data.blog_id as id, blog_data.blog_title as title, blog_data.blog_content as content, blog_data.author_id as authorid, author_data.author_name as author_name,blog_data.blog_link as blog_link, blog_data.blog_img as blog_img,blog_data.topic as topic FROM blog_data INNER JOIN author_data ON blog_data.author_id = author_data.author_id LIMIT 10 OFFSET :offset"
    blogs = db.execute(text(query), {"offset": (page-1)*10}).fetchall()
    context = convert_to_map(blogs)
    # print(context)
    return context

@app.get("/blog/{blog_id}", response_class=JSONResponse)
async def read_item(
    request: Request,blog_id: int, db: Session = Depends(get_db)
):
    query = "SELECT blog_data.blog_id as id, blog_data.blog_title as title, blog_data.blog_content as content, blog_data.author_id as authorid, author_data.author_name as author_name,blog_data.blog_link as blog_link, blog_data.blog_img as blog_img,blog_data.topic as topic FROM blog_data INNER JOIN author_data ON blog_data.author_id = author_data.author_id WHERE blog_data.blog_id = :blog_id"
    blog = db.execute(text(query), {"blog_id": blog_id}).fetchone()
    context = convert_to_map([blog])
    # print(context)
    return context[0]

# @app.get("/proxy/")
@app.get("/proxy/", response_class=HTMLResponse)
def proxy(url: str, db: Session = Depends(get_db)):
    if "medium.com" not in url:
        return {"error": "Only Medium URLs are allowed"}
    # check if the blog is already in the cache
    # Create a blog_cache table in the database if it doesn't exist
    # check if blog_cache table exists
    blog_cache_exists = db.execute(
        text("SELECT to_regclass('blog_cache')")).fetchone()
    if not blog_cache_exists[0]:
        print("Creating blog_cache table")
        blog_cache_table = """
        CREATE TABLE IF NOT EXISTS blog_cache (
            blog_url TEXT PRIMARY KEY,
            blog_cache TEXT
        )
        """
        db.execute(text(blog_cache_table))
    else:
        print("Table already exists")
    blog_cache_query = f"""
    SELECT blog_cache FROM blog_cache WHERE blog_url = '{url}'
    """
    blog_cache = db.execute(text(blog_cache_query)).fetchone()
    print(blog_cache)
    if blog_cache:
        print("From cache")
        return HTMLResponse(content=blog_cache[0])
    else:
        # Print all the blog_cache entries
        print("Not in cache")
        blog_cache_query = f"""
            SELECT blog_url FROM blog_cache
        """
        blog_cache = db.execute(text(blog_cache_query)).fetchall()
        print(blog_cache)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0 Safari/537.36",
            }
            
            # Fetch the HTML from Medium (using a headless browser if needed)
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                print("Problem guys")
                # return an html response with the error message
                return HTMLResponse(content=f"Error: {response.status_code}")
            
            # Parse the HTML with BeautifulSoup
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Optionally modify the HTML, e.g., remove unwanted elements
            # Here, you could remove ads, scripts, etc., from the page if needed
            for script in soup(["script"]):  # Remove <script> and <style> tags
                script.decompose()
            
            for anchor in soup(["a"]):
                anchor["target"] = "_blank"
            content = str(soup)
            try:
                db.execute(
                    text("INSERT INTO blog_cache (blog_url, blog_cache) VALUES (:url, :content)"),
                    {"url": url, "content": content}
                )
                db.commit()  # Commit the transaction
            except Exception as e:
                print(f"Error occurred: {e}")

            return HTMLResponse(content=content)
        except Exception as e:
            return {"error": str(e)}


@app.get("/all_posts", response_class=JSONResponse)
def ids_of_all_blogs(request: Request, db: Session = Depends(get_db)):
    try:
        query = "SELECT blog_id FROM blog_data"
        blogs = db.execute(text(query)).fetchall()
        # print([blog[0] for blog in blogs])
        return [blog[0] for blog in blogs]
    except SQLAlchemyError as e:
        print(f"Database error: {e}")
        return JSONResponse({"error": "Database error"}, status_code=500)




SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

class Account(BaseModel):
    username : str
    password : str


@app.post("/auth/login")
def login(request: Account):
    username = request.username
    password = request.password
    print("username", username)
    print("password", password)
    if username != "rajbunsha@gmail.com" or password != "raJ@123456789":
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token({"sub": username})
    refresh_token = create_access_token({"sub": username})
    print(token)
    # return {"access_token": token, "token_type": "bearer", "status_code": 200}
    return JSONResponse(content={"access_token": token, "token_type": "bearer","refresh_token":token}, status_code=200)
