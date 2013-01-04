module Language where

type Name = String

data Expr
  = EVar Name
  | EAp Expr Expr
  | EInt Int
  | ELet IsRec [(Name, Expr)] Expr
  deriving (Show)

type IsRec = Bool

type Supercomb = (Name, [Name], Expr)

type Program = [Supercomb]

