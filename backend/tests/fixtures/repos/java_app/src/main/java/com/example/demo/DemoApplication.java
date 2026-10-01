package com.example.demo;

import com.example.demo.service.GreetingService;
import org.springframework.boot.SpringApplication;

public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    public String greet(String name) {
        return new GreetingService().greet(name);
    }
}
