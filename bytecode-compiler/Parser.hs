module Parser (
  readProgram
) where

import Control.Monad
import Data.Functor.Identity
import Data.Map (Map)
import qualified Data.Map as Map
import qualified Data.List as List
import Text.Parsec
import Text.Parsec.Expr
import Text.Parsec.String
import Text.Parsec.Language
import qualified Text.Parsec.Token as T

import Language

languageDef
  = emptyDef { T.commentStart    = "{-"
             , T.commentEnd      = "-}"
             , T.nestedComments  = True
             , T.commentLine     = "--"
             , T.identStart      = lower <|> char '_'
             , T.identLetter     = alphaNum <|> char '_'
             , T.reservedNames   = [ "if"
                                   , "then"
                                   , "else"
                                   , "let"
                                   , "letrec"
                                   , "in"
                                   ]
             , T.reservedOpNames = words ("+ - * / = < <= > >= " ++
                                          "== != && || ! % ~ & | ^ " ++
                                          "<< >> :")
             , T.caseSensitive   = True
             }

lexer = T.makeTokenParser languageDef

-- Token defs
ident = T.identifier lexer
reserved = T.reserved lexer
reservedOp = T.reservedOp lexer
parens = T.parens lexer
braces = T.braces lexer
brackets = T.brackets lexer
natLit = T.natural lexer
numLit = T.naturalOrFloat lexer
strLit = T.stringLiteral lexer
chrLit = T.charLiteral lexer
semi = T.semi lexer
comma = T.comma lexer
ws = T.whiteSpace lexer

-- Syntax defs
pProgram = ws >> many pSupercomb

pSupercomb = do
  name:args <- many1 ident
  reservedOp "="
  rhs <- pExpr
  semi
  return (name, args, rhs)

pExpr = pIfExpr <|> pLetrecExpr <|> pLetExpr <|> pInfixExpr

pIfExpr = do
  reserved "if"
  e1 <- pExpr
  reserved "then"
  e2 <- pExpr
  reserved "else"
  e3 <- pExpr
  return $ EAp (EAp (EAp (EVar "if#") e1) e2) e3

pLetExpr = do
  reserved "let"
  bindings <- many pBinding
  reserved "in"
  body <- pExpr
  return $ ELet False bindings body

pLetrecExpr = do
  reserved "letrec"
  bindings <- many pBinding
  reserved "in"
  body <- pExpr
  return $ ELet True bindings body

pBinding = do
  name <- ident
  reservedOp "="
  rhs <- pExpr
  semi
  return (name, rhs)

pInfixExpr = buildExpressionParser opList pTerm

opList = [ [Infix ((reservedOp "*"  >> return (mkBinOp "*"))  <|>
                   (reservedOp "/"  >> return (mkBinOp "/"))) AssocLeft]
         , [Infix ((reservedOp "+"  >> return (mkBinOp "+"))  <|>
                   (reservedOp "-"  >> return (mkBinOp "-"))) AssocLeft]
         , [Infix  (reservedOp "<"  >> return (mkBinOp "<"))  AssocLeft]
         ]

mkBinOp ratorName lhs rhs = EAp (EAp (EVar ratorName) lhs) rhs

pTerm = do
  func <- pAtom
  args <- many (try pAtom)
  return $ foldl EAp func args

pAtom = parens pExpr
    <|> liftM EVar ident
    <|> liftM (EInt . fromIntegral) natLit

readProgram :: String -> Program
readProgram str = case parse pProgram "<Core program>" str of
  Left e -> error $ show e
  Right r -> r


