
module Compile where

import Control.Monad.State
import Control.Monad.Writer
import qualified Data.Binary as B
import Data.Int
import Data.Map (Map)
import qualified Data.Map as Map
import Data.List (sortBy)

import qualified Language as L
import Opcode

data Supercomb
  = Supercomb {
    scArity :: Int,
    scCode :: [Instr]
  }
  deriving (Show)

instance B.Binary Supercomb where
  put sc = do
    B.put (fromIntegral (scArity sc) :: Int32)
    B.put (fromIntegral (length (scCode sc)) :: Int32)
    mapM_ B.put (scCode sc)
  get = undefined

data CompilerState
  = MkState {
    scMap :: Map String Int
  }

type CompilerM = StateT CompilerState UniqueM
runCompilerM m = evalStateT m empty
  where
    empty = MkState {
      scMap = Map.empty
    }

type Unique = Int
type UniqueM = State Unique

runUniqueM m = evalState m 0

mkUnique :: UniqueM Unique
mkUnique = do
  i <- get
  put $ i + 1
  return i

primFunctions = map mk_prim_sc primFunctionDescr
  where
    mk_prim_sc (name, instr, arity) = (name, Supercomb arity instr)

compileProgram :: L.Program -> [Supercomb]
compileProgram prog = run $ do
  forM_ (zip [1..] (map fst primFunctions)) $ \(index, name) ->
    addGlobalIndex name index
  sortedProg <- liftM (map snd . sortBy sorter) (mapM scanSupercomb prog)
  compiledProg <- mapM compileSupercomb sortedProg
  entrySC <- liftM mkEntry findEntry
  return $ [entrySC] ++ map snd primFunctions ++ compiledProg
  where
    sorter (i1, _) (i2, _) = compare i1 i2
    addGlobalIndex name index = modify $ \st -> st {
      scMap = Map.insert name index (scMap st)
    }
    scanSupercomb sc@(name, _, _) = do
      index <- liftM (Map.size . scMap) get
      addGlobalIndex name (1 + index) -- #0 is the entry code
      return (index, sc)
    findEntry = do
      maybeAddr <- liftM (Map.lookup "main" . scMap) get
      case maybeAddr of
        Just index -> return index
        Nothing -> error $ "compileProgram: no main function"
    mkEntry index = Supercomb 0 [ MkArgInstr PushGlobal index
                                , MkInstr Unwind
                                ]
    run = runUniqueM . runCompilerM

compileSupercomb :: L.Supercomb -> CompilerM Supercomb
compileSupercomb (_, args, body) = do
  sc_map <- liftM scMap get
  let env = mkEnv sc_map args
  instrList <- execWriterT $ do
    compileExprStrict body env
    -- update => pop => unwind, standard epilogue for sc
    emit (MkArgInstr Update (length args))
    if not . null $ args
      then emit (MkArgInstr Pop (length args))
      else return ()
    emit (MkInstr Unwind)
  return (Supercomb (length args) instrList)

data Location
  = IsLocal Int
  | IsGlobal Int

mkEnv :: Map String Int -> [String] -> Map String Location
mkEnv globals locals = Map.union local_env global_env
  where
    local_env = Map.fromList (zip locals (map IsLocal [0..]))
    global_env = Map.map IsGlobal globals

compileExprStrict :: Monad m =>
                     L.Expr -> Map String Location -> WriterT [Instr] m ()
compileExprStrict expr env = case expr of
  L.EInt val -> emit (MkArgInstr PushInt val)
  L.ELet isRec bindings body -> 
    compileLet isRec bindings body compileExprStrict env
  L.EAp _ _ -> do
    let realAp = unwrapAp expr
    case realAp of
      [L.EVar "+", x, y] -> do
        compileExprStrict y env
        compileExprStrict x (argOffset 1 env)
        emit (MkInstr PrimIntAdd)
      [L.EVar "-", x, y] -> do
        compileExprStrict y env
        compileExprStrict x (argOffset 1 env)
        emit (MkInstr PrimIntSub)
      [L.EVar "<", x, y] -> do
        compileExprStrict y env
        compileExprStrict x (argOffset 1 env)
        emit (MkInstr PrimIntLt)
      [L.EVar "if#", x, y, z] -> do
        yInstr <- execWriterT $ compileExprStrict y env
        zInstr <- execWriterT $ compileExprStrict z env
        compileExprStrict x env
        emit (MkArgInstr PrimIntCond (1 + length yInstr))
        tell yInstr
        emit (MkArgInstr Jump (length zInstr))
        tell zInstr
      [L.EVar "seq", x, y] -> do
        compileExprStrict x env
        emit (MkArgInstr Pop 1)
        compileExprStrict y env
      _ -> as_lazy_instead
  _ -> as_lazy_instead
  where
    as_lazy_instead = do
      compileExprLazy expr env
      emit (MkInstr Eval)

compileLet isRec bindings body usingFunc env = case isRec of
  True -> compile_letrec
  False -> compile_let
  where
    compile_let = do
      letEnv <- flip execStateT env $ do
        forM_ (map snd bindings) $ \expr -> do
          currEnv <- get
          lift $ compileExprLazy expr currEnv
          put (argOffset 1 currEnv)
        forM_ (zip [0..] (map fst bindings)) $ \(index, name) -> do
          currEnv <- get
          put (Map.insert name (IsLocal index) currEnv)
      usingFunc body letEnv
      emit (MkArgInstr Slide (length bindings))

    compile_letrec = do
      emit (MkArgInstr Alloc (length bindings))
      letRecEnv <- flip execStateT (argOffset (length bindings) env) $ do
        forM_ (zip [0..] (map fst bindings)) $ \(index, name) -> do
          currEnv <- get
          put (Map.insert name (IsLocal index) currEnv)
        forM (zip [0..] (map snd bindings)) $ \(index, expr) -> do
          currEnv <- get
          lift $ compileExprLazy expr currEnv
          emit (MkArgInstr Update index)
      usingFunc body letRecEnv
      emit (MkArgInstr Slide (length bindings))

unwrapAp e = case e of
  L.EAp f a -> unwrapAp f ++ [a]
  _ -> [e]

compileExprLazy :: Monad m =>
                   L.Expr -> Map String Location -> WriterT [Instr] m ()
compileExprLazy expr env = case expr of
  L.EInt val -> emit (MkArgInstr PushInt val)
  L.EVar name -> resolveName name env
  L.ELet isRec bindings body -> 
    compileLet isRec bindings body compileExprLazy env
  L.EAp func arg -> do
    compileExprLazy arg env
    compileExprLazy func (argOffset 1 env)
    emit (MkInstr MkAp)

argOffset n = Map.map adjust_local
  where
    adjust_local location = case location of
      IsLocal i -> IsLocal $ n + i
      _ -> location

resolveName name env = case Map.lookup name env of
  Just location -> case location of 
    IsLocal i -> emit (MkArgInstr PushLocal i)
    IsGlobal i -> emit (MkArgInstr PushGlobal i)
  Nothing -> error $ "resolveName: no such name: " ++ name

emit x = tell [x]

