from sqlalchemy import (
    Column, Integer, String, ForeignKey, Boolean, DateTime, Text
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

from sqlalchemy import BigInteger

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)  # Изменено на BigInteger
    role = Column(String, nullable=False)  # 'admin', 'teacher', 'student'
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)


class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

class Poll(Base):
    __tablename__ = 'polls'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    created_by = Column(Integer, nullable=False)
    target_role = Column(String, nullable=False)  # 'teacher', 'student', 'все'
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Question(Base):
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True)
    poll_id = Column(Integer, ForeignKey('polls.id'), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String, nullable=False)

class Answer(Base):
    __tablename__ = 'answers'

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    answer_text = Column(Text, nullable=False)

class UserPollProgress(Base):
    __tablename__ = 'user_poll_progress'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    poll_id = Column(Integer, ForeignKey('polls.id'), nullable=False)
    is_completed = Column(Boolean, default=False)

class UserAnswer(Base):
    __tablename__ = 'user_answers'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    answer_text = Column(Text, nullable=False)
