document.getElementById('demo-button').onclick=async()=>{
  const button=document.getElementById('demo-button'),error=document.getElementById('demo-error');
  button.disabled=true;button.textContent='Opening your reading circle…';error.textContent='';
  try{
    const response=await fetch('/api/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    location.assign('/');
  }catch(e){error.textContent=e.message||'Your demo could not open. Please try again.';button.disabled=false;button.textContent='Try Loop as an organizer ↗';}
};
document.getElementById('login-form').onsubmit=async event=>{
  event.preventDefault();const button=document.getElementById('login-button'),error=document.getElementById('login-error');
  button.disabled=true;error.textContent='';
  try {
    const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('password').value})});
    const data=await response.json();if(!response.ok)throw new Error(data.error);
    location.assign('/');
  }catch(e){error.textContent=e.message||'The workspace is unavailable. Try again shortly.';button.disabled=false;}
};
