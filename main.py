# from typing import Optional
import time
from fastapi import FastAPI, Query, Request, Depends, Response, Header
from typing import Annotated 
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import SQLAlchemyError
# from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
import requests
from bs4 import BeautifulSoup
import models
from sqlalchemy.sql import text
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from database import engine, SessionLocal
import logging

# Configure logging
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

# File handler for logging
file_handler = logging.FileHandler("application.log")
file_handler.setLevel(logging.INFO)

# Formatter for log messages
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

# Add the file handler to the root logger
logger.addHandler(file_handler)

# Note: we should use migrations here
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
        blog_map[-1]['category'] = blog.topic
        # blog_map[-1]['rating'] = blog.rating
    return blog_map 

class Page(BaseModel):
    page: int

@app.get("/", response_class=JSONResponse)
async def read_item(page: int = 1, db: Session = Depends(get_db)):
    logger.info(f"Fetching blogs for page {page}")
    query = """
        SELECT 
            blog_data.blog_id AS id, 
            blog_data.blog_title AS title, 
            blog_data.blog_content AS content, 
            blog_data.author_id AS authorid, 
            author_data.author_name AS author_name, 
            blog_data.blog_link AS blog_link, 
            blog_data.blog_img AS blog_img, 
            blog_data.topic AS topic 
        FROM 
            blog_data 
        INNER JOIN 
            author_data 
        ON 
            blog_data.author_id = author_data.author_id 
        ORDER BY 
            blog_data.blog_id 
        LIMIT 
            10 OFFSET 
            :offset;
        """
    blogs = db.execute(text(query), {"offset": (page-1)*10}).fetchall()
    context = convert_to_map(blogs)
    logger.info(f"Fetched {len(context)} blogs for page {page}")
    return context

@app.get("/blog/{blog_id}", response_class=JSONResponse)
async def read_blog(blog_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching blog with ID {blog_id}")
    query = """
        SELECT blog_data.blog_id as id, blog_data.blog_title as title, blog_data.blog_content as content, 
        blog_data.author_id as authorid, author_data.author_name as author_name, blog_data.blog_link as blog_link, 
        blog_data.blog_img as blog_img, blog_data.topic as topic 
        FROM blog_data 
        INNER JOIN author_data 
        ON blog_data.author_id = author_data.author_id 
        WHERE blog_data.blog_id = :blog_id
        """
    blog = db.execute(text(query), {"blog_id": blog_id}).fetchone()
    if not blog:
        logger.error(f"Blog with ID {blog_id} not found")
        raise HTTPException(status_code=404, detail="Blog not found")
    context = convert_to_map([blog])
    logger.info(f"Successfully fetched blog with ID {blog_id}")
    return context[0]

@app.get("/proxy/", response_class=HTMLResponse)
def proxy(url: str, db: Session = Depends(get_db)):
    logger.info(f"Proxying URL: {url}")
    if "medium.com" not in url:
        logger.warning("Invalid URL - Only Medium URLs are allowed")
        return {"error": "Only Medium URLs are allowed"}

    blog_cache_exists = db.execute(text("SELECT to_regclass('blog_cache')")).fetchone()
    if not blog_cache_exists[0]:
        logger.info("Creating blog_cache table")
        blog_cache_table = """
        CREATE TABLE IF NOT EXISTS blog_cache (
            blog_url TEXT PRIMARY KEY,
            blog_cache TEXT
        )
        """
        db.execute(text(blog_cache_table))
    
    blog_cache_query = f"""
    SELECT blog_cache FROM blog_cache WHERE blog_url = '{url}'
    """
    blog_cache = db.execute(text(blog_cache_query)).fetchone()
    if blog_cache:
        logger.info("Returning blog from cache")
        return HTMLResponse(content=blog_cache[0])
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Error fetching URL: {response.status_code}")
                return HTMLResponse(content=f"Error: {response.status_code}")
            soup = BeautifulSoup(response.content, "html.parser")
            for script in soup(["script"]):
                script.decompose()
            for anchor in soup(["a"]):
                anchor["target"] = "_blank"
            content = str(soup)
            db.execute(text("INSERT INTO blog_cache (blog_url, blog_cache) VALUES (:url, :content)"), {"url": url, "content": content})
            db.commit()
            logger.info("Blog cached successfully")
            return HTMLResponse(content=content)
        except Exception as e:
            logger.error(f"Error during proxying: {str(e)}")
            return {"error": str(e)}

# Other routes and methods continue similarly, with logging added at key steps

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=401, detail="Could not validate credentials"
            )
        return username
    except JWTError:
        raise HTTPException(
            status_code=401, detail="Could not validate credentials"
        )

@app.post("/token", response_model=dict)
async def login(response: Response, username: str = Query(...), password: str = Query(...), db: Session = Depends(get_db)):
    logger.info(f"Attempting login for user {username}")
    # Replace this with actual user authentication logic
    user = db.execute(text("SELECT * FROM users WHERE username = :username AND password = :password"), {"username": username, "password": password}).fetchone()
    if not user:
        logger.error("Invalid username or password")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    logger.info(f"User {username} logged in successfully")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_class=JSONResponse)
async def read_users_me(token: str = Depends(oauth2_scheme)):
    username = verify_token(token)
    logger.info(f"Fetching user profile for {username}")
    return {"username": username}

def refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

class Account(BaseModel):
    username : str
    password : str

def check_credentials(username, password,db):
    query = "SELECT * FROM account WHERE email = :username AND password = :password"
    account = db.execute(text(query), {"username": username, "password": password}).fetchone()
    if account:
        return True
    return False


@app.post("/auth/login")
def login(request: Account, db: Session = Depends(get_db)):
    username = request.username
    password = request.password
    logger.info(f"Attempting login for user {username}")
    if check_credentials(username, password,db) == False:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token({"sub": username})
    refresh_token = create_access_token({"sub": username})
    print(token)
    # return {"access_token": token, "token_type": "bearer", "status_code": 200}
    return JSONResponse(content={"access_token": token, "token_type": "bearer","refresh_token":token}, status_code=200)

class Account_signup(BaseModel):
    email : str
    username : str
    password : str

@app.post("/auth/signup")
def refresh(request: Account_signup, db: Session = Depends(get_db)):
    email = request.email
    username = request.username
    password = request.password
    logger.info(f"Attempting signup for user {username}")
    # check if account table exists
    # if not, create the table
    account_table_exists = db.execute(
        text("SELECT to_regclass('account')")).fetchone()
    if not account_table_exists[0]:
        print("Creating account table")
        account_table = """
        CREATE TABLE IF NOT EXISTS account (
            id SERIAL PRIMARY KEY,
            email TEXT,
            username TEXT,
            password TEXT
        )
        """
        db.execute(text(account_table))
        db.commit()
    else:
        print("Table already exists") 
    db.execute(text("INSERT INTO account (email, username, password) VALUES (:email, :username, :password)"), {"username": username, "password": password, "email": email})
    db.commit()
    return {"status": "success"}

class Bookmark(BaseModel):
    id : int

@app.post("/bookmark")
def bookmark(headers: Annotated[str | None, Header()],bookmark:Bookmark, db: Session = Depends(get_db)):
    print(bookmark.id)
    print(headers)

    bookmark_table_exists = db.execute(
        text("SELECT to_regclass('bookmark')")).fetchone()
    if not bookmark_table_exists[0]:
        print("Creating bookmark table")
        bookmark_table = """
        CREATE TABLE IF NOT EXISTS bookmark (
            id SERIAL PRIMARY KEY,
            email TEXT,
            blog_id INT
        )
        """
        db.execute(text(bookmark_table))
        db.commit()
    else:
        print("Table already exists")
    if(db.execute(text("SELECT * FROM bookmark WHERE blog_id = :blog_id and email = :email"), {"blog_id": bookmark.id,"email": bookmark.email}).fetchone()):
        # remove the bookmark
        db.execute(text("DELETE FROM bookmark WHERE blog_id = :blog_id"), {"blog_id": bookmark.id})
        return {"status": "bookmark removed"}
    else:
        db.execute(text("INSERT INTO bookmark (blog_id) VALUES (:blog_id)"), {"blog_id": bookmark.id})
    return {"status": "success"}

# Example of logging for errors and DB connections
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up application")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application")

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"Request to {request.url.path} took {process_time:.4f} seconds")
    return response

# Replace `users`, `user_auth` and similar routes with your implementation to follow similar patterns of error handling and logs
@app.get("/logs")
def get_logs():
    logger.info("Logs endpoint called")
    try:
        with open("application.log", "r") as log_file:
            logs = log_file.readlines()
        return JSONResponse(content={"logs": logs})
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to read logs")
