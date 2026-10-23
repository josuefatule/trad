"""Use the existing B launcher only after verifying the new frozen revision."""
from .prepare import verify


if __name__ == '__main__':
    from trad_lab.m5c2b import serve
    serve.verify = verify
    serve.main()
