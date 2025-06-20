# models.py

from sqlalchemy import (
    Column, Integer, BigInteger, String, ForeignKey
)
from sqlalchemy.orm import relationship
from database import Base  # только Base!

class Group(Base):
    __tablename__ = "groups"
    id   = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    users = relationship("User", back_populates="group")
    polls = relationship("Poll", back_populates="group")

class User(Base):
    __tablename__ = "users"
    id         = Column(Integer, primary_key=True)
    tg_id      = Column(BigInteger, unique=True, index=True, nullable=False)
    role       = Column(String, nullable=False)
    group_id   = Column(Integer, ForeignKey("groups.id"), nullable=True)

    # расширенные поля ФИО (если нужны)
    surname    = Column(String, nullable=True)
    name       = Column(String, nullable=True)
    patronymic = Column(String, nullable=True)

    group = relationship("Group", back_populates="users")

class Poll(Base):
    __tablename__ = "polls"
    id          = Column(Integer, primary_key=True)
    title       = Column(String, nullable=False)
    target_role = Column(String, nullable=False)
    group_id    = Column(Integer, ForeignKey("groups.id"), nullable=True)
    created_by  = Column(BigInteger, nullable=False)

    group     = relationship("Group", back_populates="polls")
    questions = relationship("Question", back_populates="poll")

class Question(Base):
    __tablename__ = "questions"
    id            = Column(Integer, primary_key=True)
    poll_id       = Column(Integer, ForeignKey("polls.id"), nullable=False)
    question_text = Column(String, nullable=False)
    question_type = Column(String, nullable=False)

    poll    = relationship("Poll", back_populates="questions")
    answers = relationship("Answer", back_populates="question")

class Answer(Base):
    __tablename__ = "answers"
    id           = Column(Integer, primary_key=True)
    question_id  = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text  = Column(String, nullable=False)

    question = relationship("Question", back_populates="answers")

class UserPollProgress(Base):
    __tablename__ = "user_poll_progress"
    id               = Column(Integer, primary_key=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    poll_id          = Column(Integer, ForeignKey("polls.id"), nullable=False)
    last_question_id = Column(Integer, nullable=True)
    is_completed     = Column(Integer, default=0)

class UserAnswer(Base):
    __tablename__ = "user_answers"
    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id  = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text  = Column(String, nullable=False)
