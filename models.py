from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class Blogs(Base):
    __tablename__ = "blog_data"
    # blog_id,author_id,blog_title,blog_content,blog_link,blog_img,topic,scrape_time
    blog_id = Column(Integer, primary_key=True, index = True)
    blog_title = Column(String)
    blog_content = Column(String)
    blog_link = Column(String)
    blog_img = Column(String)
    scrape_time = Column(String)
    topic = Column(String)
    author_id = Column(Integer, ForeignKey("author_data.author_id"))
    # Link to the author
    author = relationship("Authors", back_populates="blogs") 

class Authors(Base):
    __tablename__ = "author_data"
    # author_id,author_name
    author_id = Column(Integer, primary_key=True, index = True)
    author_name = Column(String)

class Blog_Cache(Base):
    __tablename__ = "blog_cache"
    blog_url = Column(String, primary_key=True)
    blog_cache = Column(String)

class Ratings(Base):
    __tablename__ = "blog_ratings"
    # blog_id,userId,ratings
    blog_id = Column(Integer, ForeignKey("blog_data.blog_id"))
    userid = Column(Integer)
    rating = Column(Integer)
    # Link it to the Blogs table
    owner = relationship("Blogs", back_populates="items")

class User(Base):
    __tablename__ = "users"
    # user_id,username,password
    uid = Column(Integer, primary_key=True, index = True)
    username = Column(String)
    password = Column(String)

class Account_Ratings(Base):
    __tablename__ = "account_ratings"
    # user_id,rating
    user_id = Column(Integer, ForeignKey("users.uid"))
    rating = Column(Integer)
    # Link it to the User table
    owner = relationship("User", back_populates="items")

