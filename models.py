# models.py

from sqlalchemy import Column, Integer, BigInteger, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True, index=True)
    tg_id        = Column(BigInteger, unique=True, nullable=False, index=True)
    role         = Column(String, nullable=False)            # "admin", "teacher", "student"
    group_id     = Column(Integer, ForeignKey("groups.id"), nullable=True)
    surname      = Column(String, nullable=True)
    name         = Column(String, nullable=True)
    patronymic   = Column(String, nullable=True)

    # Связь с группой
    group        = relationship("Group", back_populates="users")


class Group(Base):
    __tablename__ = "groups"
    id     = Column(Integer, primary_key=True, index=True)
    name   = Column(String, unique=True, nullable=False)

    # Пользователи в группе
    users  = relationship("User", back_populates="group")
    # Опросы, привязанные к этой группе (если есть)
    polls  = relationship("Poll", back_populates="group")


class Poll(Base):
    __tablename__ = "polls"
    id           = Column(Integer, primary_key=True, index=True)
    title        = Column(String, nullable=False)
    target_role  = Column(String, nullable=False)           # "student", "teacher", "all"
    group_id     = Column(Integer, ForeignKey("groups.id"), nullable=True)
    created_by   = Column(BigInteger, nullable=False)       # telegram user ID

    # Связи
    group        = relationship("Group", back_populates="polls")
    questions    = relationship("Question", back_populates="poll", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    id             = Column(Integer, primary_key=True, index=True)
    poll_id        = Column(Integer, ForeignKey("polls.id"), nullable=False)
    question_text  = Column(Text, nullable=False)
    question_type  = Column(String, nullable=False)         # "text" или "single_choice"

    # Связи
    poll           = relationship("Poll", back_populates="questions")
    answers        = relationship("Answer", back_populates="question", cascade="all, delete-orphan")
    responses      = relationship("Response", back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    id            = Column(Integer, primary_key=True, index=True)
    question_id   = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text   = Column(Text, nullable=False)

    # Связи
    question      = relationship("Question", back_populates="answers")
    responses     = relationship("Response", back_populates="answer", cascade="all, delete-orphan")


class Response(Base):
    __tablename__ = "responses"
    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(BigInteger, nullable=False)     # кто отвечал
    question_id    = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_id      = Column(Integer, ForeignKey("answers.id"), nullable=True)
    response_text  = Column(Text, nullable=True)

    # Связи
    question       = relationship("Question", back_populates="responses")
    answer         = relationship("Answer",   back_populates="responses")

class PollCompletion(Base):
    __tablename__ = "poll_completions"
    __table_args__ = {"extend_existing": True}

    id       = Column(Integer, primary_key=True, index=True)
    user_id  = Column(BigInteger, nullable=False)
    poll_id  = Column(Integer, ForeignKey("polls.id"), nullable=False)

