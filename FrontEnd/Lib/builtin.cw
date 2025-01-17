(module @builtin $builtin [] :

@doc "macro for while-loop"
(macro @pub while STMT [(mparam $cond EXPR) (mparam $body STMT_LIST)] [] :
    (block _ :
        (if $cond :
            :
            (break))
        $body
        (continue)))

@doc """macro for number range for-loop,

The type of the loop variable is determined by $end"""
(macro @pub for STMT_LIST [
        (mparam $index ID)
        (mparam $start EXPR)
        (mparam $end EXPR)
        (mparam $step EXPR)
        (mparam $body STMT_LIST)] [$end_eval $step_eval $it] :
    (macro_let $end_eval (typeof $end) $end)
    (macro_let $step_eval (typeof $end) $step)
    (macro_let @mut $it (typeof $end) $start)
    (block _ :
        (if (>= $it $end_eval) :
            (break)
            :)
        (macro_let $index auto $it)
        (= $it (+ $it $step_eval))
        $body
        (continue)))


(macro @pub try STMT_LIST [
        (mparam $name ID)
        (mparam $type EXPR)
        (mparam $expr EXPR)
        (mparam $catch_name ID)
        (mparam $catch_body STMT_LIST)] [$eval] :
    (macro_let $eval auto $expr)
    (if (is $eval $type) :
        :
        (macro_let $catch_name auto
            (narrowto $eval (sumdelta (typeof $eval) $type)))
        $catch_body
        (trap))
    (macro_let $name $type (narrowto $eval $type)))

(macro swap STMT_LIST [(mparam $a EXPR) (mparam $b EXPR)] [$t] :
    (macro_let $t auto $a)
    (= $a $b)
    (= $b $t))

@doc "macro for c-style -> operator"
(macro @pub -> EXPR [(mparam $pointer EXPR) (mparam $field FIELD)] [] :
    (. (^ $pointer) $field))

)