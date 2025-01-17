@doc "heapsort"
(module main [] :
(import random)
(import fmt)

(global SIZE uint 20)


(global @mut Data auto (array_val (+ SIZE 1) r64))


(global NEWLINE auto "\n")


(global ERROR auto "ERROR\n")


(fun heap_sort [(param n uint) (param data (ptr @mut r64))] void :
    (let @mut @ref buf (array 32 u8) undef)
    (let @mut ir auto n)
    (let @mut l auto (+ (>> n 1) 1))
    (let @mut rdata r64 undef)
    (while true :
        (if (> l 1) :
            (-= l 1)
            (= rdata (^ (incp data l)))
            :
            (= rdata (^ (incp data ir)))
            (= (^ (incp data ir)) (^ (incp data 1_uint)))
            (-= ir 1)
            (if (== ir 1) :
                (= (^ (incp data ir)) rdata)
                (return)
                :))
        (let @mut i auto l)
        (let @mut j auto (<< l 1))
        (while (<= j ir) :
            (if (&& (< j ir) (< (^ (incp data j)) (^ (incp data (+ j 1))))) :
                (+= j 1)
                :)
            (if (< rdata (^ (incp data j))) :
                (= (^ (incp data i)) (^ (incp data j)))
                (= i j)
                (+= j i)
                :
                (= j (+ ir 1))))
        (= (^ (incp data i)) rdata))
    (return))


(fun dump_array [(param size uint) (param data (ptr r64))] void :
    (let @mut @ref buf (array 32 u8) undef)
    (for i 0 size 1 :
        (let v auto (^ (incp data i)))
        (fmt::print! [(wrap v fmt::r64_hex) NEWLINE]))
    (return))


(fun @cdecl main [(param argc s32) (param argv (ptr (ptr u8)))] s32 :
    (for i 0 SIZE 1 :
        (let v auto (random::get_random [1000]))
        (= (at Data (+ i 1)) v))
    (stmt (dump_array [SIZE (& (at Data 1))]))
    (fmt::print! [NEWLINE])
    (fmt::print! [SIZE NEWLINE])
    (stmt (heap_sort [SIZE (& @mut (at Data 0))]))
    (fmt::print! [NEWLINE])
    (stmt (dump_array [SIZE (& (at Data 1))]))
    (fmt::print! [NEWLINE])
    (for i 1 SIZE 1 :
        (if (> (at Data i) (at Data (+ i 1))) :
            (fmt::print! [ERROR])
            (trap)
            :))
    (return 0))

)
