(defmod macro_testing [] [

(# "Macro Examples")

(defrec pub MyRec [
    (field s1 s32 undef)
    (field s2 u32 undef)
])


(fun TestRightArrowMacro [(param pointer (ptr MyRec))] u32 [
    (return (-> pointer s2))
])
  
(fun TestWhileMacro [(param end u32)] u32 [
    (let mut sum u32 0)
    (while (< sum end) [
        (+= sum 1)
    ])
    (return sum)
])


(fun TestForMacro [(param end u32)] u32 [
    (let mut sum u32 0)
    (for i u32 0 end 1 [
        (+= sum i)
    ])
    (return sum)
])

(fun TestAssertMacro [(param xxx u32)] u32 [
    (assert (< xxx 777))
    (return 0)
])

])