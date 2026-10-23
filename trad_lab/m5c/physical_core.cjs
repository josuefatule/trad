(function(root){'use strict';
class PCMQueue{
  constructor(maxBytes=524288){this.maxBytes=maxBytes;this.buffers=[];this.bytes=0;this.offset=0;this.accepted=0;this.sent=0;this.acked=0;this.peak=0;this.pending=null;this.sequence=0;this.flushed=false;this.eof=false;this.failed=false;}
  append(buffer){
    if(this.failed||this.flushed||buffer.byteLength%2)throw Error('Invalid PCM append');
    if(this.bytes+buffer.byteLength>this.maxBytes){this.failed=true;throw Error('PCM backlog exhausted; incomplete capture');}
    if(buffer.byteLength)this.buffers.push(new Uint8Array(buffer));
    this.bytes+=buffer.byteLength;this.accepted+=buffer.byteLength;this.peak=Math.max(this.peak,this.bytes);
  }
  flush(){if(this.flushed)throw Error('Duplicate flush');this.flushed=true;}
  take(){
    if(this.failed||this.pending||this.eof)return null;
    const queued=this.accepted-this.sent;
    if(queued<64000&&!this.flushed)return null;
    if(!queued)return null;
    const result=new Uint8Array(Math.min(64000,queued));let at=0;
    while(at<result.length){const source=this.buffers[0],n=Math.min(result.length-at,source.length-this.offset);
      result.set(source.subarray(this.offset,this.offset+n),at);at+=n;this.offset+=n;
      if(this.offset===source.length){this.buffers.shift();this.offset=0;}
    }
    this.pending={frame_sequence:this.sequence++,bytes:result.length,received_bytes:this.sent+result.length,sha256:null};this.sent+=result.length;return result.buffer;
  }
  hash(sha){if(!this.pending||this.pending.sha256!==null)throw Error('Invalid hash state');this.pending.sha256=sha;}
  credit(message){
    if(!this.pending||this.pending.sha256===null||Object.entries(this.pending).some(([k,v])=>message[k]!==v)){
      this.failed=true;throw Error('Invalid PCM credit');
    }
    this.acked+=this.pending.bytes;this.bytes-=this.pending.bytes;this.pending=null;
  }
  finish(){
    if(this.failed||!this.flushed||this.pending||this.bytes||this.eof)return false;
    this.eof=true;return true;
  }
}
const api={PCMQueue};if(typeof module!=='undefined')module.exports=api;else root.M5CPhysical=api;
})(globalThis);
