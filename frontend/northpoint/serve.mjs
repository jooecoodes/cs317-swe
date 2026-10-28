// Serves only the frontend. Employee requests go directly to the hosted API.
import http from 'node:http';
import fs from 'node:fs';
const html=fs.readFileSync(new URL('./index.html',import.meta.url));
const port=Number(process.env.PORT||4173),host=process.env.HOST||'127.0.0.1';
http.createServer((request,response)=>{
 if(request.url==='/'||request.url?.startsWith('/index.html')||request.url==='/northpoint/'){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});response.end(html);}
 else{response.writeHead(404);response.end('Not found');}
}).listen(port,host,()=>console.log(`Frontend: http://localhost:${port}/#employees (employee API: https://cs317.duckdns.org)`));
