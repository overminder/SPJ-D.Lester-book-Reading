import Opcode

import Control.Monad

main = do
  forM_ opList $ \op -> do
    putStrLn $ "OP(" ++ show op ++ ")"

