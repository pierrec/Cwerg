(fun pub foo (TypeFunSig [(param a (TypeBase S32)) (param b s32) (param c s32)] s32) [
   (Comment "this is a comment with \" with quotes \t ")
   (StmtExpr (ExprCall (Id [] foo) []))
   (StmtExpr discard (ExprCall foo []))
   (return (ValNum 7 S32)) 
])

(type wrapped cool s32)



(type pub type_rec (TypeRec [
   (# "this is a comment with \" with quotes \t ")
   (field s1 s32 (ValNum 7 S32))
   (field s2 s32 (ValUndef S32))
   (field s3 s32 (ValUndef S32))
   (field s3 s32 undef_s32)

   (field b1 bool false)
   (field u1 u64 666)
   (field u2 u64 666_u64)
]))


(type  type_ptr (ptr mut s32))

(type pub type_union (TypeSum [s32 void type_ptr]))


(fun foo (TypeFunSig [(param a (TypeBase S32)) (param b s32) (param c s32)] s32) [
   (# "this is a comment with \" with quotes \t ")
    (if (Expr2 LE  a b) 
    []
    [])
   (if (<=  a b) 
    []
    [])
   (return (ValNum 7 S32)) 
])

(fun foo (TypeFunSig [(param a s32) (param b s32) (param c s32)] s32) [
   (# "this is a comment with \" with quotes \t ")
   (if (and a b) 
    [(return a)]
    [(return (xor a b))])
   (if (<=  a b) 
    []
    [])
   (return (ValNum 7 S32)) 
])


(fun foo (sig [(param a s32) (param b s32) (param c s32)]) [
   (# "this is a comment with \" with quotes \t ")
   (block my_block [
      (# "this is a comment with \" with quotes \t ")
      (break)
      (continue)
      (break my_block)
      (continue my_block)
    ])
   (return) 
])


(mod main [] [
   (# "this is a comment with \" with quotes \t ")
   (fun main (sig [(param argc uint32) (param argv (ptr u8))] s32) [
         (return 0)
   ])
])
