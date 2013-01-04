module Opcode where

import Control.Monad
import Data.Map (Map)
import qualified Data.Map as Map
import Data.Binary
import Data.Int

data Opcode
  = MkAp
  | PrimIntAdd
  | PrimIntSub
  | PrimIntLt
  | Eval
  | Unwind
  | PrimIntCond
  | Jump
  | PushInt
  | PushLocal
  | PushGlobal
  | Pop
  | Update
  | Slide
  | Alloc
  deriving (Show, Eq, Ord)

primFunctionDescr :: [(String, [Instr], Int)]
primFunctionDescr = [ ("+", mkPrimIntFunc PrimIntAdd, 2)
                    , ("-", mkPrimIntFunc PrimIntSub, 2)
                    , ("<", mkPrimIntFunc PrimIntLt, 2)
                    , ("if#", primIfFunc, 3)
                    ]

mkPrimIntFunc op = [ MkArgInstr PushLocal 1
                   , MkInstr Eval

                   , MkArgInstr PushLocal 1
                   , MkInstr Eval

                   , MkInstr op

                   , MkArgInstr Update 2
                   , MkArgInstr Pop 2
                   , MkInstr Unwind
                   ]

primIfFunc = [ MkArgInstr PushLocal 0
             , MkInstr Eval
             , MkArgInstr PrimIntCond 2

             , MkArgInstr PushLocal 1
             , MkArgInstr Jump 1
             , MkArgInstr PushLocal 2

             -- This?
             , MkInstr Eval

             , MkArgInstr Update 3
             , MkArgInstr Pop 3
             , MkInstr Unwind
             ]

-- Keep in sync with Opcode
-- Put opcode without arg in the front.
opList = [MkAp, PrimIntAdd, PrimIntSub, PrimIntLt, Eval, Unwind,
          PrimIntCond, Jump, PushInt, PushLocal, PushGlobal, Pop, Update,
          Slide, Alloc]

hasArg op = case op of
  MkAp -> False
  Unwind -> False
  _ -> True

data Instr
  = MkInstr Opcode
  | MkArgInstr Opcode Int

instance Show Instr where
  show i = case i of
    MkInstr op -> show op
    MkArgInstr op arg -> show op ++ " " ++ show arg

instrSize i = case i of
  MkInstr _ -> 1
  MkArgInstr _ _ -> 5

instance Binary Instr where
  put instr = case instr of
    MkInstr op -> do
      putWord8 (opToValue op)
    MkArgInstr op arg -> do
      putWord8 (opToValue op)
      put (fromIntegral arg :: Int32)

  get = do
    op <- liftM ((Map.!) opMap) getWord8
    if hasArg op
      then do
        arg <- get :: Get Int32
        return $ MkArgInstr op (fromIntegral arg)
      else do
        return $ MkInstr op

opValueMap = Map.fromList (zip opList [1..])
opMap = Map.fromList (zip [1..] opList)

opToValue = (Map.!) opValueMap

