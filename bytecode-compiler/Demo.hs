
import Control.Monad
import Data.Binary
import qualified Data.ByteString.Lazy as B
import Data.Int

import Language
import Parser
import Compile
import Opcode

-- Sample instr
scList = [ Supercomb 0 [ MkArgInstr PushGlobal 1
                       , MkInstr Unwind
                       ]
         , Supercomb 0 [ MkArgInstr PushInt 123
                       , MkArgInstr PushGlobal 2
                       , MkInstr MkAp
                       , MkArgInstr Update 0
                       , MkInstr Unwind
                       ]
         , Supercomb 1 [ MkArgInstr PushLocal 0
                       , MkArgInstr Update 1
                       , MkInstr Unwind
                       ]
         ]

prnScList xs = do
  B.putStr . encode $ (fromIntegral (length xs) :: Int32)
  mapM (B.putStr . encode) xs

main = do
  input <- getContents
  let prog = readProgram input
  let sc = compileProgram prog

  --putStrLn . show $ prog
  --putStrLn . show $ sc
  prnScList sc


