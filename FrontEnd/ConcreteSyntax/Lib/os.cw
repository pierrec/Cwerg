module os:

@pub rec TimeSpec:
    sec uint
    nano_sec uint

@pub @extern @cdecl fun nanosleep(req ^TimeSpec, rem ^!TimeSpec) s32:

@pub @extern @cdecl fun write(fd s32, s ^u8, size uint) sint:

@pub @extern @cdecl fun read(fd s32, s ^!u8, size uint) sint:

@pub @wrapped type Error = s32

@pub @wrapped type FD = s32

@pub global Stdin = wrapas(0, FD)

@pub global Stdout = wrapas(1, FD)

@pub global Stderr = wrapas(2, FD)

@pub fun FileWrite(fd FD, buffer slice(u8)) union(uint, Error):
    let res = write(unwrap(fd), front(buffer), len(buffer))
    if res < 0:
        return wrapas(as(res, s32), Error)
    else:
        return as(res, uint)

@pub fun FileRead(fd FD, buffer slice!(u8)) union(uint, Error):
    let res = read(unwrap(fd), front!(buffer), len(buffer))
    if res < 0:
        return wrapas(as(res, s32), Error)
    else:
        return as(res, uint)

@pub fun TimeNanoSleep(req ^TimeSpec, rem ^!TimeSpec) Error:
    let res = nanosleep(req, rem)
    return wrapas(res, Error)